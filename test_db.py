from authlibs import create_app
from authlibs.db_models import Event, EventDate
app = create_app()
with app.app_context():
    events = Event.query.all()
    for e in events:
        print(f"Event: {e.name} (ID: {e.id}, Eventbrite: {e.eventbrite_id})")
        for d in e.dates:
            print(f"  Date: {d.time_start} (Eventbrite: {d.eventbrite_id})")
