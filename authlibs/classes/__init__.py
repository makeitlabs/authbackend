from flask import Blueprint

classes_bp = Blueprint('classes', __name__, template_folder='templates', static_folder='static')

from . import classes
