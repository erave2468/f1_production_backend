-- Generated from app/models.py for MySQL 8.x
SET NAMES utf8mb4;

CREATE TABLE media_assets (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	asset_type VARCHAR(40) NOT NULL, 
	storage_key VARCHAR(512) NOT NULL, 
	public_url VARCHAR(1000), 
	mime_type VARCHAR(100), 
	width INTEGER, 
	height INTEGER, 
	alt_text VARCHAR(255), 
	source_url TEXT, 
	attribution VARCHAR(255), 
	license_note VARCHAR(255), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (storage_key)
);

CREATE TABLE seasons (
	year SMALLINT NOT NULL, 
	total_rounds SMALLINT, 
	start_date DATE, 
	end_date DATE, 
	regulations_era VARCHAR(100), 
	PRIMARY KEY (year)
);

CREATE TABLE countries (
	code VARCHAR(2) NOT NULL, 
	name_en VARCHAR(120) NOT NULL, 
	name_ko VARCHAR(120), 
	demonym_en VARCHAR(120), 
	flag_image_id BIGINT, 
	PRIMARY KEY (code), 
	FOREIGN KEY(flag_image_id) REFERENCES media_assets (id) ON DELETE SET NULL
);

CREATE TABLE circuits (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	circuit_ref VARCHAR(100) NOT NULL, 
	name VARCHAR(180) NOT NULL, 
	name_ko VARCHAR(180), 
	city VARCHAR(120), 
	country VARCHAR(120), 
	country_code VARCHAR(2), 
	latitude NUMERIC(10, 7), 
	longitude NUMERIC(10, 7), 
	length_meters INTEGER, 
	timezone VARCHAR(80), 
	opening_year SMALLINT, 
	PRIMARY KEY (id), 
	UNIQUE (circuit_ref), 
	FOREIGN KEY(country_code) REFERENCES countries (code) ON DELETE SET NULL
);

CREATE TABLE constructors (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	constructor_ref VARCHAR(80) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	full_name VARCHAR(200), 
	nationality VARCHAR(80), 
	nationality_code VARCHAR(2), 
	PRIMARY KEY (id), 
	UNIQUE (constructor_ref), 
	FOREIGN KEY(nationality_code) REFERENCES countries (code) ON DELETE SET NULL
);

CREATE TABLE drivers (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	driver_ref VARCHAR(80) NOT NULL, 
	permanent_number SMALLINT, 
	abbreviation VARCHAR(3), 
	full_name VARCHAR(160) NOT NULL, 
	nationality VARCHAR(80), 
	nationality_code VARCHAR(2), 
	date_of_birth DATE, 
	PRIMARY KEY (id), 
	UNIQUE (driver_ref), 
	FOREIGN KEY(nationality_code) REFERENCES countries (code) ON DELETE SET NULL
);

CREATE TABLE circuit_layouts (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	circuit_id BIGINT NOT NULL, 
	layout_ref VARCHAR(120) NOT NULL, 
	layout_name VARCHAR(180), 
	valid_from_year SMALLINT, 
	valid_to_year SMALLINT, 
	length_meters INTEGER, 
	corners SMALLINT, 
	map_image_id BIGINT, 
	is_current BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_circuit_layout_ref UNIQUE (layout_ref), 
	FOREIGN KEY(circuit_id) REFERENCES circuits (id) ON DELETE CASCADE, 
	FOREIGN KEY(map_image_id) REFERENCES media_assets (id) ON DELETE SET NULL
);

CREATE INDEX ix_circuit_layout_current ON circuit_layouts (circuit_id, is_current);

CREATE TABLE constructor_standings (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	season_year SMALLINT NOT NULL, 
	after_round SMALLINT NOT NULL, 
	constructor_id BIGINT NOT NULL, 
	position SMALLINT NOT NULL, 
	points NUMERIC(8, 2) NOT NULL, 
	wins SMALLINT NOT NULL, 
	podiums SMALLINT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_constructor_standing_round UNIQUE (season_year, after_round, constructor_id), 
	FOREIGN KEY(season_year) REFERENCES seasons (year) ON DELETE CASCADE, 
	FOREIGN KEY(constructor_id) REFERENCES constructors (id)
);

CREATE INDEX ix_constructor_standings_round ON constructor_standings (season_year, after_round, position);

CREATE TABLE driver_standings (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	season_year SMALLINT NOT NULL, 
	after_round SMALLINT NOT NULL, 
	driver_id BIGINT NOT NULL, 
	constructor_id BIGINT, 
	position SMALLINT NOT NULL, 
	points NUMERIC(8, 2) NOT NULL, 
	wins SMALLINT NOT NULL, 
	podiums SMALLINT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_driver_standing_round UNIQUE (season_year, after_round, driver_id), 
	FOREIGN KEY(season_year) REFERENCES seasons (year) ON DELETE CASCADE, 
	FOREIGN KEY(driver_id) REFERENCES drivers (id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (id)
);

CREATE INDEX ix_driver_standings_round ON driver_standings (season_year, after_round, position);

CREATE TABLE season_constructor_entries (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	season_year SMALLINT NOT NULL, 
	constructor_id BIGINT NOT NULL, 
	entry_name VARCHAR(180), 
	engine_name VARCHAR(180), 
	color VARCHAR(12), 
	logo_image_id BIGINT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_season_constructor UNIQUE (season_year, constructor_id), 
	FOREIGN KEY(season_year) REFERENCES seasons (year) ON DELETE CASCADE, 
	FOREIGN KEY(constructor_id) REFERENCES constructors (id) ON DELETE CASCADE, 
	FOREIGN KEY(logo_image_id) REFERENCES media_assets (id) ON DELETE SET NULL
);

CREATE TABLE season_driver_entries (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	season_year SMALLINT NOT NULL, 
	driver_id BIGINT NOT NULL, 
	constructor_id BIGINT NOT NULL, 
	color VARCHAR(12), 
	car_number SMALLINT, 
	start_round SMALLINT, 
	end_round SMALLINT, 
	is_primary_driver BOOL, 
	portrait_image_id BIGINT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_season_driver_constructor UNIQUE (season_year, driver_id, constructor_id), 
	FOREIGN KEY(season_year) REFERENCES seasons (year) ON DELETE CASCADE, 
	FOREIGN KEY(driver_id) REFERENCES drivers (id) ON DELETE CASCADE, 
	FOREIGN KEY(constructor_id) REFERENCES constructors (id) ON DELETE CASCADE, 
	FOREIGN KEY(portrait_image_id) REFERENCES media_assets (id) ON DELETE SET NULL
);

CREATE TABLE grand_prix (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	season_year SMALLINT NOT NULL, 
	circuit_id BIGINT NOT NULL, 
	circuit_layout_id BIGINT, 
	country_code VARCHAR(2), 
	round_number SMALLINT NOT NULL, 
	official_name VARCHAR(255), 
	display_name VARCHAR(180) NOT NULL, 
	display_name_ko VARCHAR(180), 
	event_format VARCHAR(40), 
	weekend_start_date DATE, 
	weekend_end_date DATE, 
	scheduled_laps SMALLINT, 
	scheduled_race_distance_meters INTEGER, 
	winning_driver_id BIGINT, 
	winning_constructor_id BIGINT, 
	status VARCHAR(40), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_gp_season_round UNIQUE (season_year, round_number), 
	FOREIGN KEY(season_year) REFERENCES seasons (year) ON DELETE CASCADE, 
	FOREIGN KEY(circuit_id) REFERENCES circuits (id), 
	FOREIGN KEY(circuit_layout_id) REFERENCES circuit_layouts (id) ON DELETE SET NULL, 
	FOREIGN KEY(country_code) REFERENCES countries (code) ON DELETE SET NULL, 
	FOREIGN KEY(winning_driver_id) REFERENCES drivers (id), 
	FOREIGN KEY(winning_constructor_id) REFERENCES constructors (id)
);

CREATE INDEX ix_gp_season_date ON grand_prix (season_year, weekend_start_date);

CREATE TABLE circuit_records (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	circuit_layout_id BIGINT NOT NULL, 
	record_type VARCHAR(32) NOT NULL, 
	driver_id BIGINT, 
	constructor_id BIGINT, 
	grand_prix_id BIGINT, 
	record_year SMALLINT, 
	lap_time_us BIGINT, 
	source VARCHAR(120), 
	source_url TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_layout_record_type UNIQUE (circuit_layout_id, record_type), 
	FOREIGN KEY(circuit_layout_id) REFERENCES circuit_layouts (id) ON DELETE CASCADE, 
	FOREIGN KEY(driver_id) REFERENCES drivers (id) ON DELETE SET NULL, 
	FOREIGN KEY(constructor_id) REFERENCES constructors (id) ON DELETE SET NULL, 
	FOREIGN KEY(grand_prix_id) REFERENCES grand_prix (id) ON DELETE SET NULL
);

CREATE TABLE driver_of_the_day (
	grand_prix_id BIGINT NOT NULL, 
	driver_id BIGINT NOT NULL, 
	vote_percentage NUMERIC(5, 2), 
	source VARCHAR(120), 
	source_url TEXT, 
	announced_at DATETIME, 
	PRIMARY KEY (grand_prix_id), 
	FOREIGN KEY(grand_prix_id) REFERENCES grand_prix (id) ON DELETE CASCADE, 
	FOREIGN KEY(driver_id) REFERENCES drivers (id)
);

CREATE TABLE grand_prix_tyre_allocations (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	grand_prix_id BIGINT NOT NULL, 
	compound_code VARCHAR(16) NOT NULL, 
	weekend_role VARCHAR(20) NOT NULL, 
	sets_per_driver SMALLINT, 
	source VARCHAR(120), 
	source_url TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_gp_tyre_compound_role UNIQUE (grand_prix_id, compound_code, weekend_role), 
	FOREIGN KEY(grand_prix_id) REFERENCES grand_prix (id) ON DELETE CASCADE
);

CREATE TABLE sessions (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	grand_prix_id BIGINT NOT NULL, 
	type ENUM('FP1','FP2','FP3','Q','SQ','S','R') NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	scheduled_start DATETIME, 
	scheduled_end DATETIME, 
	actual_start DATETIME, 
	actual_end DATETIME, 
	status VARCHAR(40), 
	total_laps SMALLINT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_gp_session_type UNIQUE (grand_prix_id, type), 
	FOREIGN KEY(grand_prix_id) REFERENCES grand_prix (id) ON DELETE CASCADE
);

CREATE INDEX ix_session_gp_start ON sessions (grand_prix_id, scheduled_start);

CREATE TABLE race_control_events (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_id BIGINT NOT NULL, 
	lap_number SMALLINT, 
	event_time DATETIME, 
	session_time_us BIGINT, 
	category VARCHAR(80), 
	event_type VARCHAR(80), 
	flag VARCHAR(40), 
	status VARCHAR(80), 
	message TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_rce_session_time ON race_control_events (session_id, session_time_us);

CREATE TABLE session_entries (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_id BIGINT NOT NULL, 
	driver_id BIGINT NOT NULL, 
	constructor_id BIGINT NOT NULL, 
	racing_number SMALLINT, 
	abbreviation VARCHAR(3), 
	grid_position SMALLINT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_session_driver UNIQUE (session_id, driver_id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(driver_id) REFERENCES drivers (id), 
	FOREIGN KEY(constructor_id) REFERENCES constructors (id)
);

CREATE TABLE weather_samples (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_id BIGINT NOT NULL, 
	sample_time DATETIME, 
	session_time_us BIGINT NOT NULL, 
	air_temperature_c NUMERIC(6, 2), 
	track_temperature_c NUMERIC(6, 2), 
	humidity_percent NUMERIC(6, 2), 
	pressure_hpa NUMERIC(8, 2), 
	wind_speed_mps NUMERIC(7, 3), 
	wind_direction_deg SMALLINT, 
	rainfall BOOL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_weather_session_time UNIQUE (session_id, session_time_us), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_weather_session_time ON weather_samples (session_id, session_time_us);

CREATE TABLE laps (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_entry_id BIGINT NOT NULL, 
	lap_number SMALLINT NOT NULL, 
	position SMALLINT, 
	lap_time_us BIGINT, 
	sector1_time_us BIGINT, 
	sector2_time_us BIGINT, 
	sector3_time_us BIGINT, 
	gap_to_leader_us BIGINT, 
	interval_to_ahead_us BIGINT, 
	compound VARCHAR(24), 
	tyre_life_laps SMALLINT, 
	stint_number SMALLINT, 
	pit_in_time_us BIGINT, 
	pit_out_time_us BIGINT, 
	track_status VARCHAR(32), 
	speed_i1_kph NUMERIC(6, 2), 
	speed_i2_kph NUMERIC(6, 2), 
	speed_fl_kph NUMERIC(6, 2), 
	speed_st_kph NUMERIC(6, 2), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_entry_lap UNIQUE (session_entry_id, lap_number), 
	FOREIGN KEY(session_entry_id) REFERENCES session_entries (id) ON DELETE CASCADE
);

CREATE INDEX ix_laps_entry_number ON laps (session_entry_id, lap_number);

CREATE TABLE pit_stops (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_entry_id BIGINT NOT NULL, 
	stop_number SMALLINT NOT NULL, 
	lap_number SMALLINT, 
	pit_entry_time_us BIGINT, 
	pit_exit_time_us BIGINT, 
	pit_lane_duration_us BIGINT, 
	stationary_duration_us BIGINT, 
	compound_before VARCHAR(24), 
	compound_after VARCHAR(24), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_entry_stop UNIQUE (session_entry_id, stop_number), 
	FOREIGN KEY(session_entry_id) REFERENCES session_entries (id) ON DELETE CASCADE
);

CREATE TABLE race_periods (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_id BIGINT NOT NULL, 
	period_type VARCHAR(40) NOT NULL, 
	start_time_us BIGINT, 
	end_time_us BIGINT, 
	start_lap SMALLINT, 
	end_lap SMALLINT, 
	start_event_id BIGINT, 
	end_event_id BIGINT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(start_event_id) REFERENCES race_control_events (id) ON DELETE SET NULL, 
	FOREIGN KEY(end_event_id) REFERENCES race_control_events (id) ON DELETE SET NULL
);

CREATE INDEX ix_race_period_session_start ON race_periods (session_id, start_time_us);

CREATE TABLE session_results (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_entry_id BIGINT NOT NULL, 
	classified_position SMALLINT, 
	displayed_position VARCHAR(8), 
	grid_position SMALLINT, 
	finishing_position SMALLINT, 
	points NUMERIC(8, 2), 
	status VARCHAR(120), 
	laps_completed SMALLINT, 
	total_time_us BIGINT, 
	gap_to_winner_us BIGINT, 
	fastest_lap_number SMALLINT, 
	fastest_lap_time BIGINT, 
	q1_time_us BIGINT, 
	q2_time_us BIGINT, 
	q3_time_us BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (session_entry_id), 
	FOREIGN KEY(session_entry_id) REFERENCES session_entries (id) ON DELETE CASCADE
);

CREATE TABLE tyre_stints (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	session_entry_id BIGINT NOT NULL, 
	stint_number SMALLINT NOT NULL, 
	compound VARCHAR(24), 
	start_lap SMALLINT NOT NULL, 
	end_lap SMALLINT NOT NULL, 
	total_laps SMALLINT GENERATED ALWAYS AS (end_lap - start_lap + 1) STORED, 
	starting_tyre_life SMALLINT, 
	ending_tyre_life SMALLINT, 
	fresh_tyre BOOL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_entry_stint UNIQUE (session_entry_id, stint_number), 
	FOREIGN KEY(session_entry_id) REFERENCES session_entries (id) ON DELETE CASCADE
);

CREATE TABLE grand_prix_sync_state (
    grand_prix_id BIGINT NOT NULL PRIMARY KEY,
    pre_event_synced_at DATETIME NULL,
    last_live_synced_at DATETIME NULL,
    post_event_synced_at DATETIME NULL
);