
## WARNING
##
## This script is only used to pull live productin data and migrate to staging
## It should NEVER be run on a production system - hence the following checks
## 

if [ `hostname` != "staging" ] ; then  echo WRONG MACHINE ; exit -1 ; fi
if [ `pwd` != "/var/www/authbackend" ] ; then  echo WRONG DIRECTORY ; exit -1 ; fi
set -e 1
set -x 1
scp -i ~bkg/.ssh/id_rsa bkg@auth:/var/www/authbackend/makeit.db .
scp -i ~bkg/.ssh/id_rsa bkg@auth:/var/www/authbackend/log.db .

###
### Database migration - Inventory system
###

# sqlite3 log.db 'CREATE TABLE IF NOT EXISTS inventorylog (
#         id INTEGER NOT NULL PRIMARY KEY,
#         purchasable_id INTEGER,
#         resource_id INTEGER,
#         member_id INTEGER,
#         time_logged DATETIME DEFAULT CURRENT_TIMESTAMP,
#         operation VARCHAR(20),
#         quantity INTEGER,
#         unit_price INTEGER,
#         total_price INTEGER,
#         old_quantity INTEGER,
#         new_quantity INTEGER,
#         comment VARCHAR(200)
# );'

# sqlite3 log.db 'CREATE INDEX IF NOT EXISTS ix_inventorylog_purchasable_id ON inventorylog (purchasable_id);'
# sqlite3 log.db 'CREATE INDEX IF NOT EXISTS ix_inventorylog_time_logged ON inventorylog (time_logged);'
# sqlite3 log.db 'CREATE INDEX IF NOT EXISTS ix_inventorylog_operation ON inventorylog (operation);'


###
### Database migration from 2.1 to 2.2
###

# Already in 2.1
#sqlite3 makeit.db 'CREATE TABLE binchoice (
#        id INTEGER NOT NULL,
#        member_id INTEGER NOT NULL,
#        location_id INTEGER NOT NULL,
#        rank  INTEGER NOT NULL,
#        PRIMARY KEY (id),
#        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
#        FOREIGN KEY(location_id) REFERENCES prostorelocations (id) ON DELETE CASCADE
#);'

#echo sqlite3 makeit.db '
#ALTER TABLE resources ADD COLUMN prodcode VARCHAR(50);
#ALTER TABLE resources ADD COLUMN price INTEGER;
#ALTER TABLE resources ADD COLUMN price_pro INTEGER;
#ALTER TABLE resources ADD COLUMN free_min INTEGER;
#ALTER TABLE resources ADD COLUMN free_min_pro INTEGER;
#'

#echo sqlite3 log.db '
#ALTER TABLE usageLog ADD COLUMN payTier INTEGER;
#'

#sqlite3 makeit.db '
#ALTER TABLE prostorelocations ADD COLUMN aruco INTEGER;
#ALTER TABLE prostorebins ADD COLUMN aruco INTEGER;
#ALTER TABLE storagegrid ADD COLUMN aruco INTEGER;
#'

#sqlite3 makeit.db '
#ALTER TABLE tools ADD COLUMN remotable BOOLEAN;
#'

#sqlite3 makeit.db '
#ALTER TABLE prostorebins ADD COLUMN status_updated_at DATETIME;
#'

#sqlite3 makeit.db '
#CREATE TABLE IF NOT EXISTS acknowledgements (
#        id INTEGER NOT NULL PRIMARY KEY,
#        resource_id INTEGER NOT NULL,
#        title VARCHAR(150),
#        message TEXT,
#        time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
#        created_by INTEGER NOT NULL,
#        enforce_on DATETIME,
#        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE,
#        FOREIGN KEY(created_by) REFERENCES members (id) ON DELETE CASCADE
#);
#CREATE TABLE IF NOT EXISTS acknowledgement_users (
#        id INTEGER NOT NULL PRIMARY KEY,
#        acknowledgement_id INTEGER NOT NULL,
#        member_id INTEGER NOT NULL,
#        token VARCHAR(100) UNIQUE NOT NULL,
#        time_sent DATETIME DEFAULT CURRENT_TIMESTAMP,
#        time_acknowledged DATETIME,
#        FOREIGN KEY(acknowledgement_id) REFERENCES acknowledgements (id) ON DELETE CASCADE,
#        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE
#);
#'

sqlite3 makeit.db '
ALTER TABLE members ADD COLUMN "group" VARCHAR(50);
'

sqlite3 makeit.db '
ALTER TABLE subscriptions ADD COLUMN "group" VARCHAR(50);
'

#sqlite3 makeit.db '
#ALTER TABLE nodes ADD COLUMN always_on BOOLEAN DEFAULT 0;
#'

#sqlite3 makeit.db '
#ALTER TABLE members ADD COLUMN plates VARCHAR(50);
#'
#
#sqlite3 makeit.db 'CREATE TABLE signs (
#	s_what VARCHAR(50),
#	s_when VARCHAR(50),
#	s_where VARCHAR(50),
#	s_desc VARCHAR(255),
#	s_qr  VARCHAR(255),
#	s_qr_desc  VARCHAR(255),
#        id INTEGER NOT NULL,
#	priority INTEGER DEFAULT 0,
#	retain INTEGER DEFAULT 0,
#	start DATETIME,
#	end DATETIME,
#        PRIMARY KEY (id)
#);
#
#INSERT INTO roles VALUES(9,"Signpost");
#'

###
### All this is TEMPORARY stuff only for STAGING 
### Do NOT Do this in production!!!! 
###

#sqlite3 makeit.db '
#INSERT INTO storageGrid VALUES(8,"Garage","Garage",6,8);
#INSERT INTO storageGrid VALUES(9,"Cleanspace","Cleanspace",4,2);
sqlite3 makeit.db '
INSERT INTO purchasable VALUES(22,"Staging Test","Staging Test Purchasable",100,"prod_MIERLuABAuCcLR","Staging Test","#test-resource-admins",5);
'

# TEST fused glass product ID is prod_UBQPgyNyWCEfPJ
sqlite3 makeit.db '
update purchasable set product="prod_UBQPgyNyWCEfPJ" where id in (9,10);
'


# Changes Brad to use my Test Stripe Account
# Test CC for Brad
sqlite3 makeit.db 'update subscriptions set customerid="cus_SmYocjOvjXSAsv", subid="sub_1RqzhBI573ycCeJ1nZmOXIII" where member_id=13;' 
# Invalid Test CC for Berndt
sqlite3 makeit.db 'update subscriptions set customerid="cus_SmYtvt8CyfFvVc", subid="sub_1Rqzm7I573ycCeJ10jCehGs5" where member_id=470;' 
#sqlite3 makeit.db 'update resources set price=1500 where id=36;' 
#sqlite3 makeit.db 'update resources set price_pro=1000, prodcode="prod_NoaY9dJVuAh41m" where id=36;' 
sqlite3 makeit.db 'update resources set prodcode="prod_NoaY9dJVuAh41m" where id=36;' 
#sqlite3 makeit.db 'update resources set free_min_pro=30 where id=36;' 

# Waterjet Product code for Brad Strip Test prod_NoaY9dJVuAh41m


# Debug data
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-02-01 00:00:00","2023-02-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-03-01 00:00:00","2023-03-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-04-01 00:00:00","2023-04-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-05-01 00:00:00","2023-05-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-04-28 01:00:00","2023-04-28 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-01 01:00:00","2023-05-01 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-01 02:00:00","2023-05-01 02:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-02 02:00:00","2023-05-02 00:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-30 02:00:00","2023-05-30 00:00:00",3600,1800,3600);'

sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (239,36,3031,"2023-04-01 00:00:00","2023-04-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (239,36,3031,"2023-05-01 00:00:00","2023-05-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (239,36,5024,"2023-04-28 01:00:00","2023-04-28 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs,payTier) VALUES (239,36,5024,"2023-05-01 01:00:00","2023-05-01 01:00:00",3600,1800,3600,1);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs,payTier) VALUES (239,36,5024,"2023-05-01 02:00:00","2023-05-01 02:00:00",3600,1800,3600,0);'

sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (470,36,5024,"2023-04-28 01:00:00","2023-04-28 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2024-01-09 01:00:00","2023-08-09 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2024-01-10 01:00:00","2023-08-10 01:00:00",3600,1800,3600);'

###
### Class Administration Schema
###
sqlite3 makeit.db '
CREATE TABLE IF NOT EXISTS events (
    id INTEGER NOT NULL PRIMARY KEY,
    eventbrite_id VARCHAR(50) UNIQUE,
    name VARCHAR(200),
    description TEXT,
    url VARCHAR(255),
    status VARCHAR(50)
);
CREATE TABLE IF NOT EXISTS event_dates (
    id INTEGER NOT NULL PRIMARY KEY,
    event_id INTEGER NOT NULL,
    eventbrite_id VARCHAR(50) UNIQUE,
    time_start DATETIME,
    time_end DATETIME,
    FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS event_instructors (
    id INTEGER NOT NULL PRIMARY KEY,
    event_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
    FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE
);
INSERT INTO roles (name) SELECT "Classes" WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name="Classes");
'
