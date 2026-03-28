from flask import Blueprint, render_template
from flask_login import login_required, current_user
from ..models import DownloadHistory

main = Blueprint('main', __name__)


@main.route('/')
def index():
    return render_template('dashboard.html')


@main.route('/history')
@login_required
def history():
    user_history = DownloadHistory.query.filter_by(user_id=current_user.id).order_by(DownloadHistory.timestamp.desc()).all()
    return render_template('history.html', history=user_history)


@main.route('/about')
def about():
    return render_template('about.html')


@main.route('/contact')
def contact():
    return render_template('contact.html')


@main.route('/help')
def help_page():
    return render_template('help.html')
