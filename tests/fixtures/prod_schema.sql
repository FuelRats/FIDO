CREATE TABLE ircsessions (
	id INTEGER NOT NULL, 
	timestamp DATETIME, 
	nickname VARCHAR, 
	hostmask VARCHAR, 
	network VARCHAR, 
	CONSTRAINT pk_ircsessions PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ircsessions_idx ON ircsessions (id);
CREATE TABLE config (
	id INTEGER NOT NULL, 
	module VARCHAR, 
	"key" VARCHAR, 
	value VARCHAR, 
	CONSTRAINT pk_config PRIMARY KEY (id)
);
CREATE UNIQUE INDEX config_idx ON config (id);
CREATE TABLE groups (
	id INTEGER NOT NULL, 
	"group" VARCHAR, 
	nickname VARCHAR, 
	number VARCHAR, 
	CONSTRAINT pk_groups PRIMARY KEY (id)
);
CREATE UNIQUE INDEX groups_idx ON groups (id);
CREATE TABLE "drones"
(
	id INTEGER
		constraint drones_pk
			primary key autoincrement,
	timestamp timestamp,
	nickname text,
	hostmask text,
	msg text
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE "messagecounter"
(
	id INTEGER
		constraint messagecounter_pk
			primary key autoincrement,
	timestamp datetime,
	nickname text,
	hostmask text,
	msg text
);
CREATE TABLE "monitor"
(
	id INTEGER
		constraint monitor_pk
			primary key autoincrement,
	timestamp datetime,
	nickname text,
	msg text
);
CREATE UNIQUE INDEX monitor_id_uindex
	on monitor (id);
CREATE TABLE asn_blacklist
(
    id        integer
        constraint table_name_pk
            primary key,
    timestamp datetime,
    asn       text,
    prefix    text,
    cidr      text,
    reason    text,
    asn_name  text
);
