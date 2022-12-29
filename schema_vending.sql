CREATE TABLE log (
	id INTEGER NOT NULL, 
	member_id INTEGER, 
	node_id INTEGER, 
	tool_id INTEGER, 
	resource_id INTEGER, 
	message VARCHAR(100), 
	doneby INTEGER, 
	time_logged DATETIME DEFAULT CURRENT_TIMESTAMP, 
	time_reported DATETIME DEFAULT CURRENT_TIMESTAMP, 
	event_type INTEGER, 
	event_subtype INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE, 
	FOREIGN KEY(node_id) REFERENCES nodes (id) ON DELETE CASCADE, 
	FOREIGN KEY(tool_id) REFERENCES tools (id) ON DELETE CASCADE, 
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE, 
	FOREIGN KEY(doneby) REFERENCES members (id) ON DELETE CASCADE
);
CREATE INDEX ix_log_time_logged ON log (time_logged);
CREATE INDEX ix_log_event_subtype ON log (event_subtype);
CREATE INDEX ix_log_time_reported ON log (time_reported);
CREATE INDEX ix_log_event_type ON log (event_type);
CREATE TABLE usagelog (
	id INTEGER NOT NULL, 
	member_id INTEGER, 
	tool_id INTEGER, 
	resource_id INTEGER, 
	time_logged DATETIME DEFAULT CURRENT_TIMESTAMP, 
	time_reported DATETIME, 
	"idleSecs" INTEGER, 
	"activeSecs" INTEGER, 
	"enabledSecs" INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE, 
	FOREIGN KEY(tool_id) REFERENCES tools (id) ON DELETE CASCADE, 
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
CREATE INDEX ix_usagelog_time_logged ON usagelog (time_logged);



# All amounts in CENTS!
CREATE TABLE vendinglog (
	id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	invoice VARCHAR(100), 
	comment VARCHAR(100), 
	doneby INTEGER, 
  oldBalance INTEGER,
  addAmount INTEGER,
  purchaseAmount INTEGER,
  surcharge INTEGER,
  totalCharge INTEGER
  newBalance INTEGER,
	time_logged DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE, 
	FOREIGN KEY(doneby) REFERENCES members (id) ON DELETE CASCADE
);
