"""RouteMind 가상 데이터 생성기.

사용법 (저장소 루트에서):
    uv run python -m data.generate                      # 기본값: 시드 42, 고객 500곳
    uv run python -m data.generate --seed 7 --customers 300

같은 시드면 언제 실행해도 똑같은 데이터가 나온다. 실험 결과를 기록할 때는
data/generated/metadata.json의 시드와 설정을 함께 남긴다.

출력 (기본 경로 data/generated/):
    customers.csv      고객 위치, 상품 유형, 수요량, 시간창, 하역 시간
    hubs.csv           후보 허브 위치, 고정비, 용량, 냉장 설비 여부
    vehicle_types.csv  차량 종류별 용량, 냉장 여부, 비용, 대수
    nodes.csv          허브 + 고객 전체 노드 목록 (거리 행렬의 행·열 순서)
    distance_km.csv    노드 간 거리 행렬(km)
    metadata.json      생성 설정과 요약 통계
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.distance import distance_matrix
from data.seoul import CANDIDATE_HUBS, DISTRICTS, SEOUL_BBOX, VEHICLE_TYPES

KM_PER_DEG_LAT = 111.32
CSV_ENCODING = "utf-8-sig"  # 엑셀에서 열어도 한글이 깨지지 않게 BOM 포함


@dataclass(frozen=True)
class Config:
    seed: int = 42
    n_customers: int = 500
    chilled_share: float = 0.25  # 냉장 상품 고객 비율
    commercial_share: float = 0.30  # 상업 고객(상점·식당) 비율, 나머지는 가정
    spread_km: float = 1.0  # 자치구 중심에서 흩어지는 정도(표준편차)
    day_start_min: int = 8 * 60  # 운영 시작 08:00 (자정부터 분)
    day_end_min: int = 20 * 60  # 운영 종료 20:00
    avg_speed_kmh: float = 25.0  # 도심 평균 주행 속도 (2단계 시간창 계산용)
    max_shift_min: int = 600  # 기사 1인 최대 근무 시간 (10시간)
    distance_method: str = "haversine"


# ---------------------------------------------------------------- 고객 생성


def _sample_locations(rng: np.random.Generator, n: int, spread_km: float) -> pd.DataFrame:
    """인구 비례로 자치구를 고르고, 그 중심 주변에 정규분포로 흩뿌린다."""
    names = np.array([d[0] for d in DISTRICTS])
    c_lat = np.array([d[1] for d in DISTRICTS])
    c_lon = np.array([d[2] for d in DISTRICTS])
    pop = np.array([d[3] for d in DISTRICTS], dtype=float)

    idx = rng.choice(len(DISTRICTS), size=n, p=pop / pop.sum())
    # km 단위 오프셋. 너무 멀리 튀지 않도록 ±2.5σ에서 자른다.
    dy, dx = np.clip(rng.normal(0.0, spread_km, size=(2, n)), -2.5 * spread_km, 2.5 * spread_km)
    lat = c_lat[idx] + dy / KM_PER_DEG_LAT
    lon = c_lon[idx] + dx / (KM_PER_DEG_LAT * np.cos(np.radians(c_lat[idx])))

    lat = np.clip(lat, SEOUL_BBOX["lat_min"], SEOUL_BBOX["lat_max"])
    lon = np.clip(lon, SEOUL_BBOX["lon_min"], SEOUL_BBOX["lon_max"])
    return pd.DataFrame({"district": names[idx], "lat": lat.round(6), "lon": lon.round(6)})


def _sample_time_windows(rng: np.random.Generator, types: np.ndarray, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """고객 유형별 희망 도착 시간창 [tw_start, tw_end] (자정부터 분).

    - 가정: 40%는 시간 무관(운영 시간 전체), 60%는 09~17시 사이 시작하는 3시간 창
    - 상업: 오전(09~12) 40%, 오후(13~17) 30%, 영업시간 전체(09~18) 30%
    """
    n = len(types)
    start = np.full(n, cfg.day_start_min)
    end = np.full(n, cfg.day_end_min)

    res = types == "residential"
    narrow = res & (rng.random(n) < 0.6)
    s = rng.integers(9, 18, size=n) * 60  # 9..17시 시작
    start[narrow], end[narrow] = s[narrow], s[narrow] + 180

    com = ~res
    choice = rng.choice(3, size=n, p=[0.4, 0.3, 0.3])
    windows = np.array([[9 * 60, 12 * 60], [13 * 60, 17 * 60], [9 * 60, 18 * 60]])
    start[com], end[com] = windows[choice[com], 0], windows[choice[com], 1]
    return start, end


def make_customers(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg.n_customers
    df = _sample_locations(rng, n, cfg.spread_km)

    ctype = np.where(rng.random(n) < cfg.commercial_share, "commercial", "residential")
    product = np.where(rng.random(n) < cfg.chilled_share, "chilled", "ambient")

    # 수요량(kg): 로그정규분포. 가정은 중앙값 12kg, 상업은 중앙값 40kg
    median = np.where(ctype == "commercial", 40.0, 12.0)
    sigma = np.where(ctype == "commercial", 0.5, 0.6)
    demand = np.clip(rng.lognormal(np.log(median), sigma), 1.0, 200.0).round(1)

    # 하역 시간(분): 기본 시간 + 무게에 비례하는 시간
    base = np.where(ctype == "commercial", 8.0, 3.0)
    service = np.round(base + 0.05 * demand).astype(int)

    tw_start, tw_end = _sample_time_windows(rng, ctype, cfg)

    df.insert(0, "customer_id", [f"C{i:04d}" for i in range(1, n + 1)])
    df["customer_type"] = ctype
    df["product_type"] = product
    df["demand_kg"] = demand
    df["service_min"] = service
    df["tw_start_min"] = tw_start
    df["tw_end_min"] = tw_end
    return df


# ---------------------------------------------------------------- 점검


def sanity_check(customers: pd.DataFrame, hubs: pd.DataFrame, vehicles: pd.DataFrame) -> list[str]:
    """최적화 문제가 처음부터 불가능(infeasible)하지 않은지 확인한다. 문제를 문자열 목록으로 반환."""
    problems = []
    total = customers["demand_kg"].sum()
    chilled = customers.loc[customers["product_type"] == "chilled", "demand_kg"].sum()

    if total > hubs["capacity_kg"].sum():
        problems.append(f"총수요 {total:,.0f}kg > 전체 허브 용량 {hubs['capacity_kg'].sum():,}kg")
    if chilled > hubs.loc[hubs["has_cold"], "capacity_kg"].sum():
        problems.append("냉장 수요가 냉장 허브 용량을 넘음")
    if customers["demand_kg"].max() > vehicles["capacity_kg"].min():
        problems.append("한 고객 수요가 가장 작은 차량 용량을 넘음 (분할 배송 필요)")
    if (customers["tw_end_min"] - customers["tw_start_min"] < customers["service_min"]).any():
        problems.append("시간창이 하역 시간보다 짧은 고객이 있음")
    return problems


# ---------------------------------------------------------------- 실행


def generate(cfg: Config, out_dir: Path) -> dict:
    rng = np.random.default_rng(cfg.seed)

    customers = make_customers(cfg, rng)
    hubs = pd.DataFrame(CANDIDATE_HUBS)
    vehicles = pd.DataFrame(VEHICLE_TYPES)

    problems = sanity_check(customers, hubs, vehicles)
    if problems:
        raise ValueError("생성된 데이터로는 문제가 성립하지 않습니다:\n- " + "\n- ".join(problems))

    nodes = pd.concat(
        [
            hubs[["hub_id", "lat", "lon"]].rename(columns={"hub_id": "node_id"}).assign(node_type="hub"),
            customers[["customer_id", "lat", "lon"]].rename(columns={"customer_id": "node_id"}).assign(node_type="customer"),
        ],
        ignore_index=True,
    )
    nodes.insert(0, "node_index", range(len(nodes)))
    dist = distance_matrix(nodes, cfg.distance_method).round(3)

    out_dir.mkdir(parents=True, exist_ok=True)
    customers.to_csv(out_dir / "customers.csv", index=False, encoding=CSV_ENCODING)
    hubs.to_csv(out_dir / "hubs.csv", index=False, encoding=CSV_ENCODING)
    vehicles.to_csv(out_dir / "vehicle_types.csv", index=False, encoding=CSV_ENCODING)
    nodes[["node_index", "node_id", "node_type", "lat", "lon"]].to_csv(out_dir / "nodes.csv", index=False, encoding=CSV_ENCODING)
    dist.to_csv(out_dir / "distance_km.csv", encoding=CSV_ENCODING)

    hub_cust = dist.loc[hubs["hub_id"], customers["customer_id"]]
    summary = {
        "n_customers": int(len(customers)),
        "n_hubs": int(len(hubs)),
        "n_nodes": int(len(nodes)),
        "total_demand_kg": round(float(customers["demand_kg"].sum()), 1),
        "chilled_demand_kg": round(float(customers.loc[customers["product_type"] == "chilled", "demand_kg"].sum()), 1),
        "chilled_customers": int((customers["product_type"] == "chilled").sum()),
        "commercial_customers": int((customers["customer_type"] == "commercial").sum()),
        "total_hub_capacity_kg": int(hubs["capacity_kg"].sum()),
        "cold_hub_capacity_kg": int(hubs.loc[hubs["has_cold"], "capacity_kg"].sum()),
        "nearest_hub_km_mean": round(float(hub_cust.min(axis=0).mean()), 2),
        "max_distance_km": round(float(dist.to_numpy().max()), 2),
    }
    meta = {"config": asdict(cfg), "summary": summary}
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def parse_args(argv: list[str] | None = None) -> tuple[Config, Path]:
    p = argparse.ArgumentParser(description="RouteMind 가상 데이터 생성기")
    p.add_argument("--seed", type=int, default=Config.seed, help="난수 시드 (기본 42)")
    p.add_argument("--customers", type=int, default=Config.n_customers, help="고객 수 (기본 500)")
    p.add_argument("--chilled-share", type=float, default=Config.chilled_share, help="냉장 고객 비율 (기본 0.25)")
    p.add_argument("--distance", choices=["haversine", "osrm"], default=Config.distance_method, help="거리 계산 방식")
    p.add_argument("--out", type=Path, default=Path("data/generated"), help="출력 폴더")
    a = p.parse_args(argv)
    cfg = Config(seed=a.seed, n_customers=a.customers, chilled_share=a.chilled_share, distance_method=a.distance)
    return cfg, a.out


def main(argv: list[str] | None = None) -> None:
    cfg, out_dir = parse_args(argv)
    meta = generate(cfg, out_dir)
    s = meta["summary"]
    print(f"[RouteMind] 데이터 생성 완료 → {out_dir}/  (seed={cfg.seed})")
    print(f"  고객 {s['n_customers']}곳 (상업 {s['commercial_customers']}, 냉장 {s['chilled_customers']}) · 후보 허브 {s['n_hubs']}곳")
    print(f"  총수요 {s['total_demand_kg']:,} kg (냉장 {s['chilled_demand_kg']:,} kg) / 허브 총용량 {s['total_hub_capacity_kg']:,} kg")
    print(f"  거리 행렬 {s['n_nodes']}×{s['n_nodes']} · 가장 가까운 허브까지 평균 {s['nearest_hub_km_mean']} km")


if __name__ == "__main__":
    main()
