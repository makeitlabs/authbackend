# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago

blueprint = Blueprint("prostore", __name__, template_folder='templates', static_folder="static",url_prefix="/prostore")



@blueprint.route('/bins', methods=['GET'])
@roles_required(['Admin','RATT'])
@login_required
def bins():
	bins=ProBin.query.all()
	return render_template('bins.html',bins=bins,bin=None)

@blueprint.route('/locations', methods=['GET'])
@roles_required(['Admin','RATT'])
@login_required
def locations():
	locs=ProLocation.query.all()
	return render_template('locations.html',locs=locs)

def register_pages(app):
	app.register_blueprint(blueprint)
