import json

import numpy as np
import pandas as pd
import pytest

from data.distance import haversine_km, haversine_matrix
from data.generate import Config, generate, main
from data.seoul import SEOUL_BBOX


# ------------------------------------------------------------- 거리


def test_one_degree_latitude_is_about_111km():
    assert haversine_km(37.0, 127.0, 38.0, 127.0) == pytest.approx(111.19, abs=0.01)


def test_seoul_city_hall_to_gangnam_station():
    # 서울시청 → 강남역 직선거리 약 8.8km
    assert haversine_km(37.5663, 126.9779, 37.4979, 127.0276) == pytest.approx(8.8, abs=0.3)


def test_matrix_is_symmetric_with_zero_diagonal():
    rng = np.random.default_rng(0)
    lat, lon = rng.uniform(37.4, 37.7, 30), rng.uniform(126.8, 127.2, 30)
    d = haversine_matrix(lat, lon)
    assert np.allclose(d, d.T)
    assert np.all(np.diag(d) == 0)
    assert np.all(d >= 0)


def test_triangle_inequality():
    rng = np.random.default_rng(1)
    d = haversine_matrix(rng.uniform(37.4, 37.7, 20), rng.uniform(126.8, 127.2, 20))
    # d[i,k] <= d[i,j] + d[j,k] 모든 i, j, k
    assert np.all(d[:, None, :] <= d[:, :, None] + d[None, :, :] + 1e-9)


# ------------------------------------------------------------- 생성기


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("gen")
    generate(Config(seed=42), out)
    return out


def _read(out, name, **kw):
    return pd.read_csv(out / name, encoding="utf-8-sig", **kw)


def test_one_command_creates_all_files(tmp_path, capsys):
    main(["--out", str(tmp_path)])
    for f in ["customers.csv", "hubs.csv", "vehicle_types.csv", "nodes.csv", "distance_km.csv", "metadata.json"]:
        assert (tmp_path / f).exists(), f
    assert "데이터 생성 완료" in capsys.readouterr().out


def test_same_seed_gives_identical_files(generated, tmp_path):
    generate(Config(seed=42), tmp_path)
    for f in ["customers.csv", "distance_km.csv", "metadata.json"]:
        assert (generated / f).read_bytes() == (tmp_path / f).read_bytes(), f


def test_different_seed_gives_different_customers(generated, tmp_path):
    generate(Config(seed=7), tmp_path)
    assert not _read(generated, "customers.csv").equals(_read(tmp_path, "customers.csv"))


def test_customers_are_valid(generated):
    c = _read(generated, "customers.csv")
    assert len(c) == 500 and c["customer_id"].is_unique
    assert c["lat"].between(SEOUL_BBOX["lat_min"], SEOUL_BBOX["lat_max"]).all()
    assert c["lon"].between(SEOUL_BBOX["lon_min"], SEOUL_BBOX["lon_max"]).all()
    assert set(c["product_type"]) == {"ambient", "chilled"}
    assert c["demand_kg"].between(1, 200).all()
    assert (c["tw_start_min"] < c["tw_end_min"]).all()
    assert c["tw_start_min"].ge(480).all() and c["tw_end_min"].le(1200).all()
    assert 0.18 < (c["product_type"] == "chilled").mean() < 0.32


def test_distance_matrix_matches_nodes(generated):
    nodes = _read(generated, "nodes.csv")
    dist = _read(generated, "distance_km.csv", index_col=0)
    assert list(dist.index) == list(nodes["node_id"]) == list(dist.columns)
    assert dist.shape == (510, 510)
    assert nodes["node_id"].iloc[0] == "H01"  # 허브가 먼저, 고객이 뒤


def test_problem_is_feasible(generated):
    meta = json.loads((generated / "metadata.json").read_text(encoding="utf-8"))
    s = meta["summary"]
    assert s["total_demand_kg"] <= s["total_hub_capacity_kg"]
    assert s["chilled_demand_kg"] <= s["cold_hub_capacity_kg"]


def test_osrm_is_not_implemented_yet(tmp_path):
    with pytest.raises(NotImplementedError):
        generate(Config(distance_method="osrm"), tmp_path)
