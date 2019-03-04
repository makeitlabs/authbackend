# vim:shiftwidth=2:expandtab

from templateCommon import *

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("example", __name__, template_folder='templates', static_folder="static",url_prefix="/example")

# --------------------------------------
# Routes
#  /test : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /test/<id> - Some ID
# --------------------------------------

@blueprint.route('/', methods = ['GET'])
@login_required
def rootpage():
	return "This is a test",200,"Content-type: text/plain"

def register_pages(app):
	app.register_blueprint(blueprint)
