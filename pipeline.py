# -*- coding: utf-8 -*-
"""mega216 build pipeline driver.

Routes:
  go_only  : PC git clone -> PC cross-compile -> upload ctx -> device docker build -> push -> smoke
  go_fe    : same + PC npm frontend build before go build (spec.prepare handled here)
  fetch_fe : download prebuilt frontend dist (npm pack / release) then go build
  java_release / php_release / node_ondevice / static / apt_sid / rust_ondevice : later waves

State: status.json  (per app: state, error, image, seconds)
Usage: python -I pipeline.py <wave-file.json> [--only key1,key2] [--limit N]
"""
import json, os, re, subprocess, sys, time, tarfile, shutil, hashlib

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SSH = os.path.join(ROOT, "ssh_exec.py")
GO = os.path.join(ROOT, "1panel_port", "toolchain", "go", "bin", "go.exe")
DL = os.path.join(HERE, "dl")
STATUS = os.path.join(HERE, "status.json")
REG = "127.0.0.1:5000/loong"

GOENV = {
    "CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": "loong64",
    "GOTOOLCHAIN": "local", "GOPROXY": "https://goproxy.cn,direct",
    "PATH": os.environ.get("PATH", ""),
}

def force_rmtree(path):
    for _ in range(3):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(1)
        # Windows: readonly files block rmtree
        import stat
        for root, dirs, files in os.walk(path):
            for f in files + dirs:
                try:
                    os.chmod(os.path.join(root, f), stat.S_IWRITE)
                except Exception:
                    pass

def load_status():
    if os.path.exists(STATUS):
        return json.load(open(STATUS, encoding="utf-8"))
    return {}

def save_status(st):
    json.dump(st, open(STATUS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def log(key, msg):
    with open(os.path.join(HERE, "logs", key + ".log"), "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    print(f"[{key}] {msg}", flush=True)

BASH = next((p for p in [shutil.which("bash")] if p and "system32" not in p.lower()), None) or "C:/Program Files/Git/bin/bash.exe"
GO = GO.replace(chr(92), "/")

def sh(cmd, cwd=None, env=None, timeout=3600):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.Popen([BASH, "-c", cmd], cwd=cwd, env=e,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors="replace")
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # kill the whole process tree (shell + git children), then drain pipes
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                       capture_output=True)
        try:
            out, _ = p.communicate(timeout=30)
        except Exception:
            out = ""
        return 124, (out or "")[-400:] + "\n[timeout]"
    return p.returncode, out or ""

def ssh(cmd, timeout=115, sudo=False):
    args = [sys.executable, SSH]
    if sudo:
        args.append("--sudo")
    args.append(cmd)
    p = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")

def ssh_put(local, remote):
    # wave27: WAN link needs minutes for big build contexts — 115s chokes them;
    # big transfers can also drop mid-flight, so retry a few times.
    for attempt in range(1, 4):
        p = subprocess.run([sys.executable, SSH, "--put", local, remote],
                           capture_output=True, text=True, errors="replace",
                           env={**os.environ, "MSYS_NO_PATHCONV": "1"}, timeout=1800)
        if p.returncode == 0:
            return True
        log("_sys", f"put attempt {attempt} failed {local}: {(p.stderr or p.stdout)[:160]}")
        time.sleep(10)
    return False

# ---------------- source acquisition ----------------

def clone(spec, srcdir):
    # git_tag overrides the clone ref while `tag` remains the image tag (store-tag substitution builds)
    repo, tag = spec["repo"], spec.get("git_tag", spec.get("tag", ""))
    if os.path.exists(srcdir) and os.listdir(srcdir):
        # wave25: validate the cached checkout actually matches the requested ref,
        # otherwise a retag rebuild silently ships the OLD source (hit on glance v0.8.8).
        if tag:
            want = ""
            for t in (tag, "v" + tag if not tag.startswith("v") else None):
                if not t:
                    continue
                for ref in (f"refs/tags/{t}^{{}}", f"refs/tags/{t}"):
                    out = sh(f'git ls-remote "{repo}" "{ref}"', timeout=60)[1]
                    line = out.strip().splitlines()[0] if out.strip() else ""
                    sha = line.split()[0] if line else ""
                    if re.fullmatch(r"[0-9a-f]{40}", sha):
                        want = sha
                        break
                if want:
                    break
            rc, cur = sh(f"git -C \"{srcdir}\" rev-parse HEAD", timeout=30)
            have = cur.strip() if rc == 0 else ""
            if want and have and want != have:
                log("_sys", f"cached {srcdir} is {have[:8]} but {tag} is {want[:8]} -> re-clone")
            elif want and have:
                return True, "cached"
            elif want and not have:
                # wave27: codeload-era cached dir without .git — cannot verify, must refetch
                log("_sys", f"cached {srcdir} is not a git checkout -> re-clone for {tag}")
            else:
                return True, "cached"
    if os.path.exists(srcdir):
        shutil.rmtree(srcdir, ignore_errors=True)
    os.makedirs(os.path.dirname(srcdir), exist_ok=True)

    def lsremote(ref):
        rc, out = sh(f'git ls-remote "{repo}" "{ref}"', timeout=60)
        if rc != 0:
            return ""
        line = out.strip().splitlines()[0] if out.strip() else ""
        sha = line.split()[0] if line else ""
        return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else ""

    sha, resolved = "", ""
    if tag:
        for t in (tag, "v" + tag if not tag.startswith("v") else None):
            if not t:
                continue
            sha = lsremote(f"refs/tags/{t}^{{}}") or lsremote(f"refs/tags/{t}")
            if sha:
                resolved = t
                break
    if not sha:
        sha = lsremote("HEAD")
        resolved = "HEAD"

    # primary path: fetch single sha (robust against clone flakiness)
    if sha:
        rc, out = sh(f'git init -q "{srcdir}" && git -C "{srcdir}" remote add origin "{repo}" '
                     f'&& git -C "{srcdir}" fetch --depth 1 origin "{sha}" '
                     f'&& git -C "{srcdir}" checkout -q FETCH_HEAD', timeout=600)
        if rc == 0:
            return True, resolved
    # fallback: codeload tarball (different endpoint, bypasses git throttling)
    m = re.match(r"https://(github\.com|gitea\.com)/(.+?)(\.git)?$", repo)
    if m:
        host, path = m.group(1), m.group(2)
        ref = resolved if resolved and resolved != "HEAD" else ""
        urls = []
        if ref:
            urls.append(f"https://codeload.{host}/{path}/tar.gz/refs/tags/{ref}")
        urls.append(f"https://codeload.{host}/{path}/tar.gz/refs/heads/master")
        urls.append(f"https://codeload.{host}/{path}/tar.gz/refs/heads/main")
        if host == "github.com" and ref:
            urls.append(f"https://codeload.github.com/{path}/tar.gz/{ref}")
        tgz = os.path.join(HERE, "dl", f"_codeload_{os.path.basename(srcdir)}.tar.gz")
        for u in urls:
            try:
                log("_sys", f"codeload fallback: {u}")
                fetch_file(u, tgz, timeout=600)
                break
            except Exception as e:
                continue
        else:
            shutil.rmtree(srcdir, ignore_errors=True)
            return False, f"clone failed: ls-remote/fetch + codeload all failed for {repo}"
        try:
            if os.path.exists(srcdir):
                shutil.rmtree(srcdir, ignore_errors=True)
            os.makedirs(srcdir)
            with tarfile.open(tgz) as t:
                members = t.getmembers()
                root = members[0].name.split("/")[0] if members else ""
                try:
                    t.extractall(srcdir, filter="data", members=[x for x in members if not x.name.startswith(root + "/.git")])
                except TypeError:
                    t.extractall(srcdir, members=members)
            inner = os.path.join(srcdir, root)
            if os.path.isdir(inner) and root:
                for item in os.listdir(inner):
                    shutil.move(os.path.join(inner, item), os.path.join(srcdir, item))
                os.rmdir(inner)
            os.remove(tgz)
            return True, resolved + "+codeload"
        except Exception as e:
            return False, f"codeload extract failed: {str(e)[:200]}"
    shutil.rmtree(srcdir, ignore_errors=True)
    return False, f"fetch failed for {repo}"

def npm_build(srcdir, spec):
    fe = os.path.join(srcdir, spec.get("fe_dir", "web"))
    if not os.path.exists(fe):
        return False, f"fe dir missing: {fe}"
    env = {"npm_config_registry": "https://registry.npmmirror.com",
           "npm_config_disturl": "https://npmmirror.com/mirrors/node/"}
    if "fe_cmds" in spec:
        cmds = spec["fe_cmds"]
    else:
        cmds = ["npm ci --no-audit --no-fund || npm install --no-audit --no-fund", "npm run build"]
    for c in cmds:
        rc, out = sh(c, cwd=fe, env=env, timeout=2400)
        if rc != 0:
            return False, f"fe cmd failed: {c}\n{out[-600:]}"
    return True, ""

# ---------------- go build ----------------

def go_build(srcdir, spec):
    bins = spec.get("bins") or []
    if not bins:
        return False, "no bins in spec"
    for b in bins:
        pkg = b.get("pkg", ".")
        out = b["out"]
        ld = b.get("ldflags", "-s -w")
        tags = f' -tags "{b["tags"]}"' if b.get("tags") else ""
        bcwd = os.path.join(srcdir, b.get("cwd", ""))
        rc, outp = sh(f'"{GO}" build -trimpath{tags} -ldflags "{ld}" -o "{out}" {pkg}',
                      cwd=bcwd, env=GOENV, timeout=2400)
        if rc != 0:
            return False, f"go build {pkg} failed\n{outp[-800:]}"
    return True, ""

# ---------------- context staging ----------------

def stage_ctx(spec, srcdir, key):
    ctx = os.path.join(HERE, "ctx", key)
    force_rmtree(ctx)
    os.makedirs(ctx, exist_ok=True)
    df = spec["dockerfile"]
    with open(os.path.join(ctx, "Dockerfile"), "w", encoding="utf-8", newline="\n") as f:
        f.write(df)
    for name, content in (spec.get("files") or {}).items():
        p = os.path.join(ctx, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    for item in spec.get("copy", []):
        s = os.path.join(srcdir, item["src"])
        d = os.path.join(ctx, item.get("dst", os.path.basename(item["src"])))
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    for b in spec.get("bins") or []:
        s = os.path.join(srcdir, b.get("cwd", ""), b["out"])
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(ctx, os.path.basename(b["out"])))
    return ctx

def alpine_df(bin, entry, cmd="", ports="", extra=""):
    return f"""# loong64 self-built (mega216)
FROM lcr.loongnix.cn/library/alpine:3.24
RUN apk add --no-cache ca-certificates tzdata 2>/dev/null || \
    (sed -i 's|dl-cdn.alpinelinux.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apk/repositories && apk add --no-cache ca-certificates tzdata)
WORKDIR /app
COPY {bin} /app/{bin}
RUN chmod +x /app/{bin}
{extra}
ENV TZ=Asia/Shanghai
{f"EXPOSE {ports}" if ports else ""}
ENTRYPOINT ["/app/{bin}"]
{f'CMD {cmd}' if cmd else ''}
"""

# ---------------- device build / push / smoke ----------------

def device_build(key, ctx, tag, timeout_min=30):
    tgz = os.path.join(HERE, "ctx", f"{key}.tgz")
    with tarfile.open(tgz, "w:gz") as t:
        t.add(ctx, arcname=".")
    if not ssh_put(tgz, f"/home/lingke/mega216/{key}.tgz"):
        return False, "upload failed"
    rc, out = ssh(f"rm -rf /home/lingke/mega216/{key} && mkdir -p /home/lingke/mega216/{key} && tar -xzf /home/lingke/mega216/{key}.tgz -C /home/lingke/mega216/{key}", timeout=115)
    img = f"{REG}/{key}:{tag}"
    ssh(f"docker rmi -f {img} >/dev/null 2>&1", timeout=60)
    bcmd = (f"setsid nohup docker build -t {img} /home/lingke/mega216/{key} "
            f"> /home/lingke/mega216/{key}.build.log 2>&1 &")
    rc, out = ssh(bcmd, timeout=20)
    if rc != 0:
        return False, f"build launch failed: {out[:200]}"
    deadline = time.time() + timeout_min * 60
    err_pat = ("ERROR:", "error:", "failed to solve", "exec format error")
    while time.time() < deadline:
        time.sleep(20)
        rc, out = ssh(f"tail -c 2000 /home/lingke/mega216/{key}.build.log 2>/dev/null; "
                      f"docker images -q {img} | head -1", timeout=40)
        idline = out.strip().splitlines()[-1].strip() if out.strip() else ""
        if len(idline) == 12:
            return True, img
        low = out.lower()
        if any(p in low for p in err_pat):
            return False, "build error: " + out[-500:]
        if "writing image" in low or "naming to" in low:
            time.sleep(8)
            rc, out2 = ssh(f"docker images -q {img} | head -1", timeout=30)
            if out2.strip():
                return True, img
    return False, "build timeout"

def device_push(img, key):
    rc, out = ssh(f"docker push {img} 2>&1 | tail -2", timeout=115)
    if "digest" in out or "The push refers" in out:
        return True, img
    # big images may exceed 115s; launch detached push and poll
    ssh(f"setsid nohup docker push {img} > /home/lingke/mega216/{key}.push.log 2>&1 &", timeout=20)
    for _ in range(20):
        time.sleep(30)
        rc, out = ssh(f"tail -c 500 /home/lingke/mega216/{key}.push.log 2>/dev/null", timeout=40)
        if "digest:" in out:
            return True, img
        if "error" in out.lower() and "denied" not in out.lower():
            return False, "push error: " + out[-300:]
    return False, "push timeout"

def device_smoke(key, spec, img):
    smoke = spec.get("smoke") or {}
    name = f"smoke-{key}"
    stype = smoke.get("type", "")
    envs = "".join(f" -e {k}='{v}'" for k, v in (smoke.get("env") or {}).items())

    if stype == "cmd":
        args = " ".join(smoke.get("cmd") or [])
        # wave27: EXIT=$? after a pipe is tail's status (always 0) — use PIPESTATUS[0]
        rc, out = ssh(f"docker run --rm --name {name}{envs} {img} {args} 2>&1 | tail -c 300; echo EXIT=${{PIPESTATUS[0]}}", timeout=90)
        last = out.strip().splitlines()[-1] if out.strip() else ""
        if last == "EXIT=0":
            return True, f"cmd ok: {out.strip().splitlines()[0][:80] if out.strip() else ''}"
        return False, f"cmd: {out[-300:]}"

    vols = "".join(f" -v {v}" for v in (smoke.get("volumes") or []))
    rc, out = ssh(f"docker rm -f {name} >/dev/null 2>&1; docker run -d --name {name}{envs}{vols} {img} 2>&1", timeout=60)
    wait = int(smoke.get("wait", 5))
    time.sleep(wait)
    _rc, state = ssh(f"docker inspect -f {{{{.State.Running}}}} {name} 2>/dev/null; "
                     f"docker logs {name} 2>&1 | tail -c 400", timeout=60)
    lines = state.strip().splitlines()
    running = lines[0].strip() == "true" if lines and lines[0].strip() in ("true", "false") else False
    logs = "\n".join(lines[1:]) if len(lines) > 1 else ""
    ok, detail = False, ""
    if stype == "http":
        ports = spec.get("ports") or ["80"]
        p = str(ports[0]).split(":")[0]
        _rc2, out2 = ssh(f"docker exec {name} sh -c 'command -v curl >/dev/null && curl -s -o /dev/null -w %{{http_code}} http://127.0.0.1:{p}{smoke.get('path','/')} || (wget -q -O- http://127.0.0.1:{p}{smoke.get('path','/')} | head -c 1 && echo HTTP_OK); echo'", timeout=45)
        body = out2.strip()
        if body and body[-3:].isdigit():
            ok, detail = True, f"http {body[-3:]}"
        elif "HTTP_OK" in body:
            ok, detail = True, "http ok (wget)"
        elif running:
            ok, detail = True, f"running (no probe result: {body[:60]})"
        else:
            detail = f"exited: {logs[-300:]}"
    else:
        if running:
            ok, detail = True, "process running"
        else:
            detail = f"exited: {logs[-300:]}"
    ssh(f"docker rm -f {name} >/dev/null 2>&1", timeout=30)
    return ok, detail

# ---------------- routes ----------------

def route_go(spec, key, status):
    srcdir = os.path.join(DL, key)
    ok, msg = clone(spec, srcdir)
    if not ok:
        return False, f"clone failed: {msg}"
    for c in spec.get("prepare") or []:
        rc, out = sh(c, cwd=srcdir, timeout=1800)
        if rc != 0:
            return False, f"prepare failed: {c}\n{out[-400:]}"
    if spec.get("fe_dir"):
        ok, msg = npm_build(srcdir, spec)
        if not ok:
            return False, msg
    ok, msg = go_build(srcdir, spec)
    if not ok:
        return False, msg
    if not spec.get("dockerfile"):
        b = spec["bins"][0]
        spec["dockerfile"] = alpine_df(b["out"], entry=b["out"], extra=spec.get("df_extra", ""),
                                       ports=spec.get("ports", ""), cmd=spec.get("df_cmd", ""))
    ctx = stage_ctx(spec, srcdir, key)
    tag = spec.get("tag", "latest")
    ok, img = device_build(key, ctx, tag)
    if not ok:
        return False, img
    ok, msg = device_push(img, key)
    if not ok:
        return False, msg
    ok, detail = device_smoke(key, spec, img)
    return ok, f"{img} smoke={detail}"

def _copy_artifacts(spec, ddir, ctx):
    for item in spec.get("copy", []):
        s = os.path.join(ddir, item["src"])
        d = os.path.join(ctx, item.get("dst", os.path.basename(item["src"])))
        if item.get("extract") and (s.endswith(".zip") or s.endswith(".tgz") or s.endswith(".tar.gz")):
            if s.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(s) as z:
                    z.extractall(d)
            else:
                os.makedirs(d, exist_ok=True)
                with tarfile.open(s) as t:
                    try:
                        t.extractall(d, filter="data")
                    except TypeError:
                        t.extractall(d)
            # flatten a single top-level directory (release zips/tarballs)
            entries = os.listdir(d)
            if len(entries) == 1 and os.path.isdir(os.path.join(d, entries[0])):
                inner = os.path.join(d, entries[0])
                tmp = d + "_flatten"
                shutil.move(inner, tmp)
                os.rmdir(d)
                shutil.move(tmp, d)
            continue
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)

# ---------------- artifact route (download release asset -> stage -> build) ----------------

def fetch_file(url, dest, timeout=1800):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "loong64-build/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    return os.path.getsize(dest)

def route_artifact(spec, key, status):
    ddir = os.path.join(DL, "_art", key)
    os.makedirs(ddir, exist_ok=True)
    for f in spec.get("fetch") or []:
        dest = os.path.join(ddir, f["name"])
        if os.path.exists(dest) and os.path.getsize(dest) == f.get("size", -1) and f.get("size"):
            continue
        log(key, f"fetch {f['url']}")
        n = fetch_file(f["url"], dest)
        log(key, f"fetched {f['name']} {n//1024//1024}MB")
    ctx = os.path.join(HERE, "ctx", key)
    if os.path.exists(ctx):
        shutil.rmtree(ctx, ignore_errors=True)
    os.makedirs(ctx)
    with open(os.path.join(ctx, "Dockerfile"), "w", encoding="utf-8", newline="\n") as fo:
        fo.write(spec["dockerfile"])
    for name, content in (spec.get("files") or {}).items():
        p = os.path.join(ctx, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(content)
    # when the context is assembled on the device, only Dockerfile/files stay local
    if not spec.get("device_extract"):
        _copy_artifacts(spec, ddir, ctx)
    for c in spec.get("ctx_cmds") or []:
        rc, out = sh(c, cwd=ctx, timeout=600)
        if rc != 0:
            return False, f"ctx_cmd failed: {c}\n{out[-300:]}"
    tag = spec.get("tag", "latest")
    if spec.get("device_extract"):
        # assemble build context on device (avoids Windows MAX_PATH on big zips)
        bdir = f"/home/lingke/mega216/{key}/b"
        ssh(f"rm -rf /home/lingke/mega216/{key} && mkdir -p {bdir}", timeout=40)
        for item in spec.get("copy", []):
            local = os.path.join(ddir, item["src"])
            if os.path.exists(local):
                if not ssh_put(local, f"{bdir}/{item.get('dst', item['src'])}"):
                    return False, f"device upload failed: {item['src']}"
        tmpd = os.path.join(HERE, "ctx", f"{key}_remote")
        os.makedirs(tmpd, exist_ok=True)
        with open(os.path.join(tmpd, "Dockerfile"), "w", encoding="utf-8", newline="\n") as fo:
            fo.write(spec["dockerfile"])
        for name, content in (spec.get("files") or {}).items():
            with open(os.path.join(tmpd, name), "w", encoding="utf-8", newline="\n") as fo:
                fo.write(content)
        if not ssh_put(os.path.join(tmpd, "Dockerfile"), f"{bdir}/Dockerfile"):
            return False, "device upload failed: Dockerfile"
        for name in (spec.get("files") or {}):
            ssh_put(os.path.join(tmpd, name), f"{bdir}/{name}")
        rc, out = ssh(f"bash -c 'cd {bdir} && chmod +x *.sh 2>/dev/null; true'", timeout=30)
        img = f"{REG}/{key}:{tag}"
        ssh(f"docker rmi -f {img} >/dev/null 2>&1", timeout=60)
        ssh(f"setsid nohup docker build -t {img} {bdir} > /home/lingke/mega216/{key}.build.log 2>&1 &", timeout=20)
        deadline = time.time() + 60 * 60
        ok, img = False, img
        while time.time() < deadline:
            time.sleep(25)
            rc, out = ssh(f"tail -c 1500 /home/lingke/mega216/{key}.build.log 2>/dev/null; docker images -q {img} | head -1", timeout=40)
            idline = out.strip().splitlines()[-1].strip() if out.strip() else ""
            if len(idline) == 12:
                ok = True
                break
            low = out.lower()
            if any(p in low for p in ("ERROR:", "error:", "failed to solve", "exec format error")):
                return False, "build error: " + out[-500:]
        if not ok:
            return False, "build timeout"
    else:
        ok, img = device_build(key, ctx, tag)
    if not ok:
        return False, img
    ok, msg = device_push(img, key)
    if not ok:
        return False, msg
    ok, detail = device_smoke(key, spec, img)
    return ok, f"{img} smoke={detail}"

# ---------------- static route (npm build -> busybox httpd) ----------------

BUSYBOX_STATIC_DF = """# loong64 self-built (mega216 static)
FROM lcr.loongnix.cn/library/busybox:latest
COPY site /srv
EXPOSE 80
CMD ["httpd","-f","-p","80","-h","/srv"]
"""

def route_static(spec, key, status):
    srcdir = os.path.join(DL, key)
    ok, msg = clone(spec, srcdir)
    if not ok:
        return False, f"clone failed: {msg}"
    env = {"npm_config_registry": "https://registry.npmmirror.com",
           "npm_config_disturl": "https://npmmirror.com/mirrors/node/"}
    for c in spec.get("prepare") or []:
        rc, out = sh(c, cwd=srcdir, env=env, timeout=2400)
        if rc != 0:
            return False, f"prepare failed: {c}\n{out[-500:]}"
    fe = os.path.join(srcdir, spec.get("fe_dir", "."))
    if "build_cmds" in spec:
        cmds = spec["build_cmds"]
    else:
        cmds = ["npm ci --no-audit --no-fund || npm install --no-audit --no-fund", "npm run build"]
    for c in cmds:
        rc, out = sh(c, cwd=fe, env=env, timeout=3000)
        if rc != 0:
            return False, f"build cmd failed: {c}\n{out[-500:]}"
    dist = os.path.join(srcdir, spec.get("dist_dir", "dist"))
    if not os.path.exists(dist):
        return False, f"dist dir missing: {dist}"
    ctx = os.path.join(HERE, "ctx", key)
    force_rmtree(ctx)
    os.makedirs(ctx, exist_ok=True)
    shutil.copytree(dist, os.path.join(ctx, "site"),
                    ignore=shutil.ignore_patterns(".git", ".github", ".gitignore"))
    with open(os.path.join(ctx, "Dockerfile"), "w", encoding="utf-8", newline="\n") as fo:
        fo.write(spec.get("dockerfile") or BUSYBOX_STATIC_DF)
    tag = spec.get("tag", "latest")
    ok, img = device_build(key, ctx, tag)
    if not ok:
        return False, img
    ok, msg = device_push(img, key)
    if not ok:
        return False, msg
    ok, detail = device_smoke(key, spec, img)
    return ok, f"{img} smoke={detail}"

# ---------------- node-ondevice route (clone -> upload -> device npm build) ----------------

def node_df(entry, ports="", extra="", cmd=""):
    if isinstance(ports, list):
        ports = " ".join(str(p) for p in ports)
    base = f"""# loong64 self-built (mega216 node)
FROM lcr.loongnix.cn/library/node:v20.19.3-debian
ENV npm_config_registry=https://registry.npmmirror.com npm_config_disturl=https://npmmirror.com/mirrors/node/ TZ=Asia/Shanghai
{extra}
COPY app /app
WORKDIR /app
RUN (npm ci --omit=dev --no-audit --no-fund || npm install --omit=dev --no-audit --no-fund)
RUN chmod +x {entry} 2>/dev/null || true
{f"EXPOSE {ports}" if ports else ""}
"""
    if entry.startswith("node "):
        base += f'ENTRYPOINT ["sh","-c","{entry}"]\n'
        if cmd:
            base += f'CMD {cmd}\n'
    else:
        base += f'ENTRYPOINT ["{entry}"]\n'
        if cmd:
            base += f'CMD {cmd}\n'
    return base

def route_node(spec, key, status):
    srcdir = os.path.join(DL, key)
    ok, msg = clone(spec, srcdir)
    if not ok:
        return False, f"clone failed: {msg}"
    env = {"npm_config_registry": "https://registry.npmmirror.com",
           "npm_config_disturl": "https://npmmirror.com/mirrors/node/"}
    for c in spec.get("pc_build") or []:
        rc, out = sh(c, cwd=os.path.join(srcdir, spec.get("app_dir", ".")), env=env, timeout=3000)
        if rc != 0:
            return False, f"pc_build failed: {c}\n{out[-500:]}"
    ctx = os.path.join(HERE, "ctx", key)
    force_rmtree(ctx)
    os.makedirs(ctx, exist_ok=True)
    appdir = os.path.join(srcdir, spec.get("app_dir", "."))
    shutil.copytree(appdir, os.path.join(ctx, "app"),
                    ignore=shutil.ignore_patterns(".git", ".github", ".gitignore", "node_modules"))
    entry = spec.get("entry", "node server/server.js")
    df = spec.get("dockerfile") or node_df(entry, ports=spec.get("ports", ""),
                                           extra=spec.get("df_extra", ""),
                                           cmd=spec.get("df_cmd", ""))
    with open(os.path.join(ctx, "Dockerfile"), "w", encoding="utf-8", newline="\n") as fo:
        fo.write(df)
    tag = spec.get("tag", "latest")
    ok, img = device_build(key, ctx, tag, timeout_min=45)
    if not ok:
        return False, img
    ok, msg = device_push(img, key)
    if not ok:
        return False, msg
    ok, detail = device_smoke(key, spec, img)
    return ok, f"{img} smoke={detail}"

# ---------------- rust-ondevice route (clone -> upload -> device cargo build) ----------------

def route_rust(spec, key, status):
    srcdir = os.path.join(DL, key)
    ok, msg = clone(spec, srcdir)
    if not ok:
        return False, f"clone failed: {msg}"
    for c in spec.get("prepare") or []:
        rc, out = sh(c, cwd=srcdir, timeout=900)
        if rc != 0:
            return False, f"prepare failed: {c} | {out[-400:]}"
    appdir = os.path.join(srcdir, spec.get("app_dir", "."))
    ctx = os.path.join(HERE, "ctx", key)
    force_rmtree(ctx)
    os.makedirs(ctx, exist_ok=True)
    shutil.copytree(appdir, os.path.join(ctx, "app"),
                    ignore=shutil.ignore_patterns(".git", ".github", ".gitignore", "target"))
    with open(os.path.join(ctx, "Dockerfile"), "w", encoding="utf-8", newline="\n") as fo:
        fo.write(spec["dockerfile"])
    for name, content in (spec.get("files") or {}).items():
        with open(os.path.join(ctx, name), "w", encoding="utf-8", newline="\n") as fo:
            fo.write(content)
    tag = spec.get("tag", "latest")
    ok, img = device_build(key, ctx, tag, timeout_min=90)
    if not ok:
        return False, img
    ok, msg = device_push(img, key)
    if not ok:
        return False, msg
    ok, detail = device_smoke(key, spec, img)
    return ok, f"{img} smoke={detail}"

ROUTES = {"go_only": route_go, "go_fe": route_go, "fetch_fe": route_go,
          "artifact": route_artifact, "static": route_static, "node": route_node,
          "rust": route_rust}

def main():
    wave_file = sys.argv[1]
    only = None
    limit = 0
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--only":
            only = set(args[i+1].split(","))
            i += 2
        elif args[i] == "--limit":
            limit = int(args[i+1])
            i += 2
        else:
            i += 1
    specs = json.load(open(os.path.join(HERE, wave_file), encoding="utf-8"))
    status = load_status()
    done = 0
    for spec in specs:
        key = spec["key"]
        if only and key not in only:
            continue
        if limit and done >= limit:
            break
        prev = status.get(key, {})
        if prev.get("state") == "built":
            log(key, "skip (already built)")
            continue
        route = spec["route"]
        fn = ROUTES.get(route)
        if not fn:
            log(key, f"route {route} not implemented yet")
            continue
        t0 = time.time()
        log(key, f"=== start ({route}) tag={spec.get('tag')}")
        try:
            ok, msg = fn(spec, key, status)
        except Exception as e:
            ok, msg = False, f"exception: {type(e).__name__} {str(e)[:300]}"
        secs = int(time.time() - t0)
        status[key] = {"state": "built" if ok else "failed", "msg": msg[:500],
                       "route": route, "secs": secs}
        save_status(status)
        log(key, f"=== {'OK' if ok else 'FAIL'} ({secs}s) {msg[:200]}")
        done += 1
    json.dump(status, open(STATUS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    built = sum(1 for v in status.values() if v.get("state") == "built")
    print(f"\nwave done. total built={built}")

if __name__ == "__main__":
    main()
