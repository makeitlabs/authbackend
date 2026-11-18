# Project

This is a Pyhton3 w/ Flask application to do member and membership managment for a makerspace, including member access to facilities and equipment, and integration into payment and waiver tracking.

# Running and testing

You are not going to be able to run this. Too many dependencies on stuff that probably doesn't exist on this system. You can try a quick python unit test of something or compile, but don't try to "run" the whole pacakge or to install stuff required to get the full code up and running.

Agent is NOT running on the actual production system. There is no database and no ini file with config.

# Layout

Most of the important code is in authlibs. Each directory in here is generally a high level UI category or functions (members, resources, nodes, waivers, etc). There is typically a single file in here that is a Flask blueprint that defines the web pages use for those, and static/ and template/ directories for Flask content.

Each library generally follows very standard patterns for GUI pages, templates and database usage - so you can look across these to see common patterns and elements.

User access validity is a more complex concept. It is generally calculated *dynamically* from common functions, looking directly at database content.

Database is db_models.py - which defines the database schema used throughout

# Inventory

Inventory is a bit of a mess. There are two different inventory systems. One is for consumables (like 3d printer filament, etc) and the other is for tools (like 3d printers, laser cutters, etc). They are not well integrated.

# Database Updates

If you need to update the database schema, updates should be captured in the pulldb.sh file. This file will be used by _user_ to update database and schema for testing, and this is the primary way to specify how schema changes are to be made for production.

# Reports
authlibs/reports/reports.py allows a bunch of misc reports to be generated. Note that the actual *list* and definitions of reports is in templates/reports.html, and each report has a separate .py file in the reports directory.

These reports were intented to be simple free-standing text reports. The main report GUI will wrap these in `<pre>` and `</pre>` tags to render within the web site properly. We have since tried to add better visual formatting to these reports allowing ones in HTML. This means that any such report must start with a `</pre>` and end with a `<pre>` to work within the tags that the GUI framework will wrap them in, to allow such formatting.

We have also started to add some optional parameters to reports, making things such as date pickers available in the GUI list, which can be passed to the report script as a parameter. Adding these kind of parameters in GUI should be concidered when adding new reports.