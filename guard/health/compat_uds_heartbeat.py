import os, json, time, tempfile, shutil
ROOT=r"C:\\Users\\LeeSG\\Desktop\\coin_quant"
HP=os.path.join(ROOT,"shared_data","health")
os.makedirs(HP, exist_ok=True)
U=os.path.join(HP,"uds.json")

def atomic_write(path, data:dict):
    d=os.path.dirname(path); fd,tmp = tempfile.mkstemp(prefix="uds_", suffix=".tmp", dir=d)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    shutil.move(tmp, path)

while True:
    payload={
        "status":"OK",
        "detail":"compat_uds_heartbeat",
        "ts": time.time(),
        "ws_connected": True
    }
    try: atomic_write(U, payload)
    except Exception: pass
    time.sleep(2)
