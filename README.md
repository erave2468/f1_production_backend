# F1 Production Backend

FastF1 데이터를 AWS RDS(MySQL)에 적재하고 FastAPI로 프론트엔드에 제공하기 위한 EC2 배포용 백엔드입니다.

## 1. 실행 구조

```text
EC2 boot
  ├─ f1-api.service
  │    ├─ ExecStartPre: python -m app.bootstrap
  │    │    ├─ CREATE DATABASE IF NOT EXISTS f1db
  │    │    └─ SQLAlchemy Base.metadata.create_all() -> 24 tables
  │    └─ Gunicorn + uvicorn_worker -> FastAPI (127.0.0.1:8000)
  │
  ├─ nginx -> :80/:443 -> 127.0.0.1:8000
  │
  └─ f1-collector.timer
       └─ f1-collector.service -> python -m app.sync
            ├─ FastF1 reference/schedule
            ├─ 종료된 미수집 세션
            └─ 챔피언십 순위

RDS MySQL
  └─ F1 24-table schema
```

FastF1 수집은 별도 systemd oneshot/timer에서 수행합니다.

## 2. 주요 파일

```text
app/
  main.py                    FastAPI 앱
  config.py                  환경변수 / RDS / Secrets Manager 설정
  db.py                      SQLAlchemy engine/session + DB 생성
  bootstrap.py               서버 시작 전 DB/schema bootstrap
  models.py                  24개 SQLAlchemy ORM 테이블
  collect.py                 수동 수집 CLI
  sync.py                    자동 증분 수집
  ingest/
    fastf1_collector.py      FastF1 -> DB 적재
    helpers.py
  api/
    schemas.py               Pydantic response model
    services.py              SQLAlchemy 조회/조합
    routes/
      grandprix.py
      championship.py
      circuit.py

deploy/
  nginx/f1-api.conf
  systemd/f1-api.service
  systemd/f1-collector.service
  systemd/f1-collector.timer
  scripts/
    install_amazon_linux_2023.sh
    install_app.sh
    enable_services.sh
    update_server.sh
```

## 3. API

```text
GET /health
GET /ready

GET /api/grandprix?season=2026
GET /api/grandprix/{grand_prix_id}
GET /api/grandprix/{grand_prix_id}/overview
GET /api/grandprix/{grand_prix_id}/result
GET /api/grandprix/{grand_prix_id}/history?session=R
GET /api/grandprix/{grand_prix_id}/detail?session=R

GET /api/championship/driver?season=2026
GET /api/championship/constructor?season=2026

GET /api/circuit/{circuit_id}
```

Swagger:

```text
http://15.164.170.239/docs
```

## 4. FastF1 적재 범위

자동 적재:

- seasons
- drivers
- constructors
- circuits
- grand_prix
- sessions
- season_driver_entries
- season_constructor_entries
- session_entries
- session_results
- laps
- tyre_stints
- pit_stops
- weather_samples
- race_control_events
- driver_standings
- constructor_standings
- SpeedI1 / SpeedI2 / SpeedFL / SpeedST -> laps

FastF1만으로 완전 자동화하지 않는 메타데이터:

- media_assets (국기/드라이버/팀/서킷 이미지)
- countries의 flag_image_id
- circuit_layouts의 길이/코너/맵 이미지 등 정적 메타데이터
- grand_prix_tyre_allocations의 GP 사전 컴파운드 배정
- driver_of_the_day
- circuit_records


