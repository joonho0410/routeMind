"""노드 간 거리 행렬 계산.

지금은 지구를 구로 보고 두 점 사이의 대원 거리(하버사인)를 쓴다.
실제 도로 거리보다 짧게 나오므로, 나중에 OSRM 도로 거리로 바꿀 때는
`distance_matrix()`의 method만 추가하면 나머지 코드는 그대로 쓸 수 있게 했다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088  # 평균 지구 반지름 (IUGG)


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """두 지점(또는 지점 배열) 사이의 하버사인 거리(km).

    a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
    d = 2R · arcsin(√a)
    """
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = phi2 - phi1
    dlmb = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def haversine_matrix(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """n개 지점의 n×n 거리 행렬. 브로드캐스팅으로 반복문 없이 한 번에 계산한다."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    d = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    np.fill_diagonal(d, 0.0)
    return d


def distance_matrix(nodes: pd.DataFrame, method: str = "haversine") -> pd.DataFrame:
    """nodes(node_id, lat, lon)로 거리 행렬(km)을 만든다. 행·열 이름은 node_id."""
    if method == "haversine":
        d = haversine_matrix(nodes["lat"].to_numpy(), nodes["lon"].to_numpy())
    elif method == "osrm":
        raise NotImplementedError(
            "OSRM 도로 거리는 아직 구현 전입니다 (계획상 여유가 생기면 교체). "
            "지금은 --distance haversine 을 사용하세요."
        )
    else:
        raise ValueError(f"알 수 없는 거리 계산 방식: {method}")
    ids = nodes["node_id"].to_list()
    return pd.DataFrame(d, index=pd.Index(ids, name="node_id"), columns=ids)
