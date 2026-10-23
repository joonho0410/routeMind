"""가상 데이터의 고정 입력값: 서울 자치구, 후보 허브, 차량 종류.

여기 있는 값은 '그럴듯한 가정'이지 실제 통계가 아니다.
- 자치구 좌표는 구청 근처의 대략적인 위치, 인구는 만 명 단위 근삿값이며
  고객을 뽑을 때의 가중치로만 쓴다.
- 허브 비용·용량, 차량 비용은 시나리오 분석을 위해 정한 값이다.
값을 바꾸면 README의 '데이터 명세'와 '가정'도 함께 고친다.
"""

from __future__ import annotations

# 서울 경계 상자 (위도, 경도). 고객 좌표가 이 밖으로 나가지 않게 자른다.
SEOUL_BBOX = {
    "lat_min": 37.413,
    "lat_max": 37.715,
    "lon_min": 126.764,
    "lon_max": 127.184,
}

# (자치구, 위도, 경도, 인구[만 명])
DISTRICTS: list[tuple[str, float, float, int]] = [
    ("종로구", 37.5735, 126.9790, 14),
    ("중구", 37.5641, 126.9979, 13),
    ("용산구", 37.5326, 126.9905, 21),
    ("성동구", 37.5633, 127.0371, 28),
    ("광진구", 37.5385, 127.0823, 34),
    ("동대문구", 37.5744, 127.0400, 34),
    ("중랑구", 37.6066, 127.0927, 38),
    ("성북구", 37.5894, 127.0167, 43),
    ("강북구", 37.6396, 127.0257, 29),
    ("도봉구", 37.6688, 127.0471, 30),
    ("노원구", 37.6542, 127.0568, 50),
    ("은평구", 37.6027, 126.9291, 46),
    ("서대문구", 37.5791, 126.9368, 30),
    ("마포구", 37.5663, 126.9019, 36),
    ("양천구", 37.5170, 126.8664, 43),
    ("강서구", 37.5509, 126.8495, 56),
    ("구로구", 37.4954, 126.8874, 40),
    ("금천구", 37.4569, 126.8955, 23),
    ("영등포구", 37.5264, 126.8962, 38),
    ("동작구", 37.5124, 126.9393, 38),
    ("관악구", 37.4784, 126.9516, 48),
    ("서초구", 37.4837, 127.0324, 40),
    ("강남구", 37.5172, 127.0473, 54),
    ("송파구", 37.5145, 127.1059, 65),
    ("강동구", 37.5301, 127.1238, 46),
]

# 후보 허브 10곳. 외곽일수록 개설비가 싸고 도심일수록 비싸다고 가정한다.
# fixed_cost_krw: 하루 단위로 환산한 개설·운영 고정비(원)
# capacity_kg:    하루 처리 가능 물량(kg)
# has_cold:       냉장 보관 설비 여부. 냉장 상품은 이 값이 True인 허브만 처리 가능
CANDIDATE_HUBS: list[dict] = [
    {"hub_id": "H01", "name": "강서 마곡", "district": "강서구", "lat": 37.5610, "lon": 126.8250, "fixed_cost_krw": 1_300_000, "capacity_kg": 5000, "has_cold": True},
    {"hub_id": "H02", "name": "구로", "district": "구로구", "lat": 37.4950, "lon": 126.8700, "fixed_cost_krw": 1_200_000, "capacity_kg": 3500, "has_cold": False},
    {"hub_id": "H03", "name": "금천 가산", "district": "금천구", "lat": 37.4780, "lon": 126.8850, "fixed_cost_krw": 1_250_000, "capacity_kg": 4000, "has_cold": True},
    {"hub_id": "H04", "name": "영등포", "district": "영등포구", "lat": 37.5170, "lon": 126.9050, "fixed_cost_krw": 1_700_000, "capacity_kg": 3000, "has_cold": False},
    {"hub_id": "H05", "name": "마포 상암", "district": "마포구", "lat": 37.5780, "lon": 126.8900, "fixed_cost_krw": 1_500_000, "capacity_kg": 3000, "has_cold": False},
    {"hub_id": "H06", "name": "성동 성수", "district": "성동구", "lat": 37.5450, "lon": 127.0550, "fixed_cost_krw": 1_800_000, "capacity_kg": 3000, "has_cold": True},
    {"hub_id": "H07", "name": "도봉 창동", "district": "도봉구", "lat": 37.6530, "lon": 127.0480, "fixed_cost_krw": 1_100_000, "capacity_kg": 4000, "has_cold": False},
    {"hub_id": "H08", "name": "송파 문정", "district": "송파구", "lat": 37.4850, "lon": 127.1200, "fixed_cost_krw": 1_600_000, "capacity_kg": 4500, "has_cold": True},
    {"hub_id": "H09", "name": "서초 양재", "district": "서초구", "lat": 37.4650, "lon": 127.0400, "fixed_cost_krw": 1_900_000, "capacity_kg": 3500, "has_cold": True},
    {"hub_id": "H10", "name": "강동 고덕", "district": "강동구", "lat": 37.5600, "lon": 127.1550, "fixed_cost_krw": 1_250_000, "capacity_kg": 4000, "has_cold": False},
]

# 차량 종류. 냉장차는 상온 상품도 실을 수 있다고 가정한다.
# fixed_cost_krw: 하루 투입 고정비(차량 리스·기사 일당 등)
# cost_per_km_krw: 주행 거리당 변동비(유류·소모품)
VEHICLE_TYPES: list[dict] = [
    {"vehicle_type": "V1", "name": "1톤 탑차", "capacity_kg": 1000, "refrigerated": False, "fixed_cost_krw": 110_000, "cost_per_km_krw": 300, "count": 20},
    {"vehicle_type": "V2", "name": "1톤 냉장탑차", "capacity_kg": 900, "refrigerated": True, "fixed_cost_krw": 140_000, "cost_per_km_krw": 350, "count": 10},
    {"vehicle_type": "V3", "name": "2.5톤 탑차", "capacity_kg": 2500, "refrigerated": False, "fixed_cost_krw": 170_000, "cost_per_km_krw": 450, "count": 6},
]
