from authlibs import db_models
from authlibs.init import create_app
import datetime
from sqlalchemy import or_

app = create_app()
with app.app_context():
    # 1. Check member
    member = db_models.Member.query.filter(db_models.Member.member.ilike('%Crew1%')).first()
    print("Member:", member.id if member else "None", member.member if member else "")

    # 2. Check Resource
    r = db_models.Resource.query.filter(db_models.Resource.name == 'hamshack-door-users').first()
    print("Resource hamshack-door-users:", r.id if r else "None")

    # 3. Check Logs for member and resource
    if member and r:
        logs = db_models.Logs.query.filter(
            db_models.Logs.member_id == member.id,
            db_models.Logs.resource_id == r.id
        ).order_by(db_models.Logs.time_logged.desc()).limit(3).all()
        for log in logs:
            print("Log:", log.id, log.event_type, log.time_logged)

    # 4. Check AccessByMember
    if member and r:
        acc = db_models.AccessByMember.query.filter(
            db_models.AccessByMember.member_id == member.id,
            db_models.AccessByMember.resource_id == r.id
        ).all()
        for a in acc:
            print("Access:", a.id, "active=", a.active, "level=", a.level)

    # 5. Check Marc doorbot
    marcr = db_models.Resource.query.filter(db_models.Resource.name == 'doorbot-marc').first()
    print("Resource doorbot-marc:", marcr.id if marcr else "None")
    marc_mem = db_models.Member.query.filter(db_models.Member.member.ilike('%Steven%')).first()
    if marc_mem and marcr:
        acc2 = db_models.AccessByMember.query.filter(
            db_models.AccessByMember.member_id == marc_mem.id,
            db_models.AccessByMember.resource_id == marcr.id
        ).all()
        print("Steven Access to marc:")
        for a in acc2:
            print("Access:", a.id, "active=", a.active, "level=", a.level)

