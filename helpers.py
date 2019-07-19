from flask import session, request, redirect, url_for
from functools import wraps

def login_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if session.get("user_id") is None:
			return redirect(url_for('login'))
		return f(*args, **kwargs)
	return decorated_function


def not_empty(title, author, isbn):
	if title != "" and author != "" and isbn != "":
		return True
	else:
		return False	