import json, time, os, tempfile, shutil

ROOT=r"C:\\Users\\LeeSG\\Desktop\\coin_quant"
SD  = os.path.join(ROOT, "shared_data")
HP  = os.path.join(SD, "health")

P={
  "agg"    : os.path.join(SD, "health.json"),
  "databus": os.path.join(SD, "databus_snapshot.json"),
  "feeder" : os.path.join(HP, "feeder.json"),
  "trader" : os.path.join(HP, "trader.json"),
  "uds"    : os.path.join(HP, "uds.json"),
}

TH = {
  "feeder": 6,   # s
  "uds"   : 6,   # s (Trader 판정 핵심)
  "databus": 10, # s
}

def age(p):
    try: return max(0, int(time.time() - os.path.getmtime(p)))
    except FileNotFoundError: return None

def load_json(p):
    try:
        with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except: return {}

def atomic_write(p, data):
    d=os.path.dirname(p); fd,tmp = tempfile.mkstemp(dir=d, prefix="h_", suffix=".tmp")
    with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
    shutil.move(tmp,p)

while True:
    base = load_json(P["agg"])

    # 필수 섹션 보장
    base.setdefault("price",{}); base.setdefault("databus",{}); base.setdefault("ares",{})

    # age 계산
    a_databus = age(P["databus"])
    a_feeder  = age(P["feeder"])
    a_traderJ = age(P["trader"])
    a_uds     = age(P["uds"])

    # UI가 읽는 값 주입
    if a_databus is not None:
        base["price"]["age_sec"]   = a_databus
        base["databus"]["age_sec"] = a_databus
    # ARES는 일단 health.json의 갱신으로 대체(없으면 databus와 동일)
    base["ares"]["age_sec"] = a_databus if a_databus is not None else base["ares"].get("age_sec", None)

    # feeder/trader OK 판정
    feeder_ok = (a_feeder is not None and a_feeder < TH["feeder"])
    t_status  = load_json(P["trader"]).get("status")  # GREEN/YELLOW/RED or None
    trader_ok = ((a_uds is not None and a_uds < TH["uds"]) and (t_status != "RED"))

    base["feeder_ok"] = feeder_ok
    base["trader_ok"] = trader_ok
    base["ws_connected"] = bool(feeder_ok)

    # 글로벌
    if feeder_ok and trader_ok: gs="GREEN"
    elif feeder_ok or trader_ok: gs="YELLOW"
    else: gs="RED"
    base["global_status"]=gs
    base["ts"]=time.time()

    try: atomic_write(P["agg"], base)
    except: pass

    time.sleep(3)
