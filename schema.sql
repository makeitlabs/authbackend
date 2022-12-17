CREATE TABLE roles (
        id INTEGER NOT NULL,
        name VARCHAR(50),
        PRIMARY KEY (id),
        UNIQUE (name)
);
CREATE TABLE kvopts (
        id INTEGER NOT NULL,
        keyname VARCHAR(50),
        "default" VARCHAR(50),
        kind VARCHAR(50),
        options VARCHAR,
        description VARCHAR(100),
        "displayOrder" INTEGER,
        PRIMARY KEY (id)
);
CREATE TABLE blacklist (
        id INTEGER NOT NULL,
        entry VARCHAR(50),
        entrytype VARCHAR(50),
        reason VARCHAR(50),
        updated_date DATETIME,
        PRIMARY KEY (id)
);
CREATE TABLE members (
        id INTEGER NOT NULL,
        member VARCHAR(50),
        email VARCHAR(50),
        alt_email VARCHAR(50),
        firstname VARCHAR(50),
        slack VARCHAR(50),
        lastname VARCHAR(50),
        phone VARCHAR(50),
        "plan" VARCHAR(50),
        access_enabled INTEGER,
        access_reason VARCHAR(50),
        active INTEGER,
        nickname VARCHAR(50),
        stripe_name VARCHAR(50),
        time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
        time_updated DATETIME,
        warning_sent DATETIME,
        warning_level INTEGER,
        email_confirmed_at DATETIME,
        membership VARCHAR(50),
        password VARCHAR(255), dob DATETIME, memberFolder VARCHAR(255),
        PRIMARY KEY (id),
        UNIQUE (member),
        UNIQUE (membership)
);
CREATE TABLE nodes (
        id INTEGER NOT NULL,
        name VARCHAR(20),
        mac VARCHAR(20), last_ping datetime, strength INTEGER, last_update DATETIME,
        PRIMARY KEY (id)
);
CREATE TABLE resourcealiases (
        id INTEGER NOT NULL,
        alias VARCHAR(50),
        resource_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (alias),
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
CREATE TABLE tags_by_member (
        id INTEGER NOT NULL,
        tag_ident VARCHAR(50),
        tag_type VARCHAR(50),
        tag_name VARCHAR(50),
        updated_date DATETIME,
        member VARCHAR(50),
        member_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE
);
CREATE TABLE subscriptions (
        id INTEGER NOT NULL,
        paysystem VARCHAR(50),
        subid VARCHAR(50) NOT NULL,
        customerid VARCHAR(50) NOT NULL,
        name VARCHAR(50),
        email VARCHAR(50),
        "plan" VARCHAR(50),
        expires_date DATETIME,
        created_date DATETIME,
        updated_date DATETIME,
        checked_date DATETIME,
        active INTEGER,
        membership VARCHAR(50) NOT NULL,
        member_id INTEGER, rate_plan VARCHAR(50),
        PRIMARY KEY (id),
        UNIQUE (membership),
        FOREIGN KEY(member_id) REFERENCES members (id)
);
CREATE TABLE waivers (
        id INTEGER NOT NULL,
        waiver_id VARCHAR(50),
        firstname VARCHAR(50),
        lastname VARCHAR(50),
        email VARCHAR(50),
        member_id INTEGER,
        created_date DATETIME, waivertype Integer, emergencyName VARCHAR(50), emergencyPhone VARCHAR(50),
        PRIMARY KEY (id),
        FOREIGN KEY(member_id) REFERENCES members (id)
);
CREATE TABLE userroles (
        id INTEGER NOT NULL,
        member_id INTEGER,
        role_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE
);
CREATE TABLE nodeconfig (
        id INTEGER NOT NULL,
        value VARCHAR(50),
        node_id INTEGER,
        key_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(node_id) REFERENCES nodes (id) ON DELETE CASCADE,
        FOREIGN KEY(key_id) REFERENCES kvopts (id) ON DELETE CASCADE
);
CREATE TABLE oauth (
        id INTEGER NOT NULL,
        provider VARCHAR(50),
        created_at DATETIME,
        token TEXT,
        user_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES members (id)
);
CREATE TABLE tools (
        id INTEGER NOT NULL,
        name VARCHAR(50),
        lockout VARCHAR(100),
        short VARCHAR(20),
        node_id INTEGER,
        resource_id INTEGER, displayname VARCHAR(50),
        PRIMARY KEY (id),
        UNIQUE (name),
        UNIQUE (short),
        FOREIGN KEY(node_id) REFERENCES nodes (id) ON DELETE CASCADE,
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
CREATE TABLE accessbymember (
        id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        resource_id INTEGER NOT NULL,
        is_active BOOLEAN DEFAULT '1' NOT NULL,
        time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
        time_updated DATETIME,
        comment VARCHAR(255) DEFAULT '',
        lockout_reason VARCHAR(255),
        lockouts VARCHAR(255) DEFAULT '',
        permissions VARCHAR(255) DEFAULT '',
        created_by VARCHAR(25) DEFAULT 'admin' NOT NULL,
        level INTEGER,
        PRIMARY KEY (id),
        CONSTRAINT _member_resource_uc UNIQUE (member_id, resource_id),
        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE,
        CHECK (is_active IN (0, 1))
);
CREATE TABLE apikeys (
        id INTEGER NOT NULL,
        name VARCHAR(50) NOT NULL,
        username VARCHAR(50) NOT NULL,
        password VARCHAR(50),
        tool_id INTEGER, acl VARCHAR(255),
        PRIMARY KEY (id),
        FOREIGN KEY(tool_id) REFERENCES tools (id) ON DELETE CASCADE
);
CREATE TABLE maintsched (
        id INTEGER NOT NULL,
        name VARCHAR(50),
        "desc" VARCHAR(100),
        realtime_span INTEGER,
        realtime_unit VARCHAR(12),
        machinetime_span INTEGER,
        machinetime_unit VARCHAR(12),
        resource_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
CREATE TABLE prostorelocations (
        location VARCHAR(50) NOT NULL,
        id INTEGER NOT NULL,
        loctype INTEGER NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (location)
);
CREATE TABLE prostorebins (
        id INTEGER NOT NULL,
        member_id INTEGER,
        name VARCHAR(20),
        status INTEGER NOT NULL,
        location_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (name),
        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(location_id) REFERENCES prostorelocations (id) ON DELETE CASCADE
);
CREATE TABLE training (
        id INTEGER NOT NULL,
        name VARCHAR(150),
        hours INTEGER,
        permit INTEGER,
        days INTEGER,
        url VARCHAR(150),
        required INTEGER,
        required_endorsements VARCHAR(50),
        endorsements VARCHAR(50),
        resource_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(required) REFERENCES resources (id) ON DELETE CASCADE,
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "resources" (
        id INTEGER NOT NULL,
        name VARCHAR(50),
        short VARCHAR(20),
        description VARCHAR(50),
        owneremail VARCHAR(50),
        last_updated DATETIME,
        slack_chan VARCHAR(50),
        slack_admin_chan VARCHAR(50),
        info_url VARCHAR(150),
        info_text VARCHAR(150),
        slack_info_text VARCHAR,
        age_restrict INTEGER,
        permissions VARCHAR(255),
        PRIMARY KEY(id),
        UNIQUE (name),
        UNIQUE (short)
);
CREATE TABLE quizquestion (
        id INTEGER NOT NULL,
        question TEXT,
        answer TEXT,
        idx INTEGER,
        training_id INTEGER NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(training_id) REFERENCES training (id) ON DELETE CASCADE
);
CREATE TABLE tempauth (
        id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        admin_id INTEGER NOT NULL,
        resource_id INTEGER NOT NULL,
        expires DATETIME,
        timesallowed INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(admin_id) REFERENCES members (id) ON DELETE CASCADE,
        FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);
