import os
import requests

from flask import Flask, session, render_template, flash, redirect, request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash

from helpers import login_required, not_empty

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
@login_required
def index():
	"""Redirects user to search page"""

	return redirect("/search")


@app.route("/register", methods=["GET", "POST"])
def register():
	"""Register user"""

	# User reached route via POST (by submitting a form)
	if request.method == "POST":
		
		username = request.form.get("username")
		
		# Ensure that the user entered a username in the form
		if not username:
			message = "You didn't provide a username!"
			return render_template("error.html", message = message)

		password = request.form.get("password")
		
		# Ensure that the user entered a password in the form
		if not password:
			message = "You didn't provide a password!"
			return render_template("error.html", message = message)

		confirmation = request.form.get("confirmation")
		
		# Ensure that the user confirmed the password
		if not confirmation:
			message = "You didn't confirm your password!"
			return render_template("error.html", message = message)

		# Ensure that the two passwords match
		if confirmation != password:
			message = "Passwords don't match!"
			return render_template("error.html", message = message)

		# Hashing the password
		password = generate_password_hash(password)
		
		# Checking if username already exists
		check_user = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone()

		
		# If the username is not taken, create new user - else, inform the user to provide a new username
		if check_user is None:
			new_user = db.execute("INSERT INTO users (username, password) VALUES (:username, :password)", {"username": username, "password": password})
			db.commit()

		else:	
			message = "Username taken! Provide a new username!"
			return render_template("error.html", message = message)

		rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchall()

		session["user_id"] = rows[0]["id"]

		return redirect("/search")

	else:	
		return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
	"""User logs in"""

	# User reached route via POST (by submitting a form)
	if request.method == "POST":

		username = request.form.get("username")

		# Ensure that the user entered a username in the form
		if not username:
			message = "You didn't provide a username!"
			return render_template("error.html", message = message)

		password = request.form.get("password")
		
		# Ensure that the user entered a password in the form
		if not password:
			message = "You didn't provide a password!"
			return render_template("error.html", message = message)

		rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchall()

		# Checking if username and password are correct
		if (len(rows) != 1) or not (check_password_hash(rows[0]["password"], password)):
			message = "Invalid username and/or password!"
			return render_template("error.html", message = message)

		# Remember which user is logged in
		session["user_id"] = rows[0]["id"]
		
		return redirect("/search")	
	
	else:
		return render_template("login.html")


@app.route("/logout")
def logout():
	"""Clear the session"""
	
	session.clear()

	return redirect("/")


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
	"""User searches for books"""

	# User reached route via post (by submitting a form)
	if request.method == "POST":

		title = request.form.get("title")
		author = request.form.get("author")
		isbn = request.form.get("isbn")

		if title == "" and author == "" and isbn == "":
			message = "You didn't provide any data for the book!"
			return render_template("error.html", message = message)

		# Transforming the input so that it can be used by the LIKE keyword in SQL
		if title != "":	
			title = '%' + title + '%'
		
		if author != "":
			author = '%' + author + '%'
		
		if isbn != "":	
			isbn = '%' + isbn + '%'

		books = db.execute("SELECT title, author, year, isbn FROM books WHERE title LIKE :title OR author LIKE :author OR isbn LIKE :isbn ORDER BY year DESC", {"title": title, "author": author, "isbn": isbn}).fetchall()
		
		if len(books) == 0:
			return render_template("not_found.html")
		else:
			return render_template("results.html", books = books)		
    
	else:
		return render_template("search.html")


@app.route('/book/<string:isbn>', methods = ["GET", "POST"])
@login_required
def book(isbn):
	"""User gets info for the book, and has the opportunity to review it"""
	
	# Sending an API request to goodreads.com
	res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "gwRyrKSkd1VvqI3NSac1Iw", "isbns": isbn})

	# Checking if isbn is valid and escaping a potential json.decoder error
	try:
		res = res.json()
	except:
		message = "Invalid ISBN"
		return render_template("error.html", message = message)	

	# Parsing the results
	res = res["books"]
	res = res[0]

	# Keys in res:
	# 	'id'
	# 	'isbn'
	# 	'isbn13'
	# 	'ratings_count'
	# 	'reviews_count',
	# 	'text_reviews_count'
	# 	'work_ratings_count'
	# 	'work_reviews_count'
	# 	'work_text_reviews_count'
	# 	'average_rating'

	# Fetching the book from our database
	book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()

	if len(book) == 0:
		message = "Sorry, there is no book with that ISBN"
		return render_template("error.html", message = message)

	book_id = book["id"]
	title = book["title"]
	author = book["author"]
	year = book["year"]

	# Appending the title, author and year to the results we got from the API request
	res["title"] = title
	res["author"] = author
	res["year"] = year

	book = res

	user_id = session["user_id"]

	# Querying the database for reviews that users have left for the specific book
	review_list = db.execute("SELECT username, review FROM reviews JOIN users ON reviews.user_id = users.id WHERE book_id = :book_id", {"book_id": book_id}).fetchall()

	# Send message to book.html on whether there are or aren't any reviews for the book
	if len(review_list) == 0:
		others = False
	else:
		others = True

	# Checking if the user has alreay rated and reviewed the book
	review_col = db.execute("SELECT rating, review FROM reviews WHERE book_id = :book_id AND user_id = :user_id", {"book_id": book_id, "user_id": user_id}).fetchall()

	if len(review_col) == 0:
		no_rating = True
		no_review = True
	else:
		if review_col[0]["rating"] == None and review_col[0]["review"] == None:
			no_rating = True
			no_review = True
		elif review_col[0]["review"] == None and review_col[0]["rating"] != None:
			no_review = True
			no_rating = False
		elif review_col[0]["rating"] == None and review_col[0]["review"] == None:
			no_rating = True	
		else:
			no_rating = False
			no_review = False		

		
	# User reached route via post (by submitting a form)
	if request.method == "POST":

		rating = request.form.get("rating")
		if not rating:
			message = "You must provide a rating for this book!"
			return render_template("error.html", message = message)

		review = request.form.get("review")
		if not review:
			message = "You must provide a review for this book!"
			return render_template("error.html", message = message)

		# Checking if the user has already rated and reviewed the book
		review_col = db.execute("SELECT rating, review FROM reviews WHERE book_id = :book_id AND user_id = :user_id", {"book_id": book_id, "user_id": user_id}).fetchall()

		# If the user hasn't rated and/or reviewed the book, let him do that
		if len(review_col) == 0:
			db.execute("INSERT INTO reviews (book_id, user_id, rating, review) VALUES (:book_id, :user_id, :rating, :review)", {"book_id": book_id, "user_id": user_id, "rating": rating, "review": review})
			db.commit()
		else:
			if review_col[0]["rating"] == None and review_col[0]["review"] == None:
				db.execute("UPDATE reviews SET rating = :rating, review = :review WHERE book_id = :book_id AND user_id = :user_id", {"rating": rating, "review": review, "book_id": book_id, "user_id": user_id})
				db.commit()
			elif review_col[0]["review"] == None and review_col[0]["rating"] != None:
				db.execute("UPDATE reviews SET review = :review WHERE book_id = :book_id AND user_id = :user_id", {"review": review, "book_id": book_id, "user_id": user_id})
				db.commit()
			elif review_col[0]["review"] != None and review_col[0]["rating"] == None:
				db.execute("UPDATE reviews SET rating = :rating WHERE book_id = :book_id AND user_id = :user_id", {"rating": rating, "book_id": book_id, "user_id": user_id})
				db.commit()	
			else:
				message = "You have already rated and reviewed this book!"
				return render_template("error.html", message = message)

		# Check for users' ratings and reviews
		review_list = db.execute("SELECT username, review FROM reviews JOIN users ON reviews.user_id = users.id WHERE book_id = :book_id", {"book_id": book_id}).fetchall()

		if len(review_list) == 0:
			others = False
		else:
			others = True

		review_col = db.execute("SELECT rating, review FROM reviews WHERE book_id = :book_id AND user_id = :user_id", {"book_id": book_id, "user_id": user_id}).fetchall()

		if len(review_col) == 0:
			no_rating = True
			no_review = True
		else:
			if review_col[0]["rating"] == None and review_col[0]["review"] == None:
				no_rating = True
				no_review = True
			elif review_col[0]["review"] == None and review_col[0]["rating"] != None:
				no_review = True
				no_rating = False
			elif review_col[0]["rating"] == None and review_col[0]["review"] == None:
				no_rating = True	
			else:
				no_rating = False
				no_review = False
	
	return render_template("book.html", book = book, no_rating = no_rating, no_review = no_review, others = others, review_list = review_list)


@app.route("/api/<string:isbn>", methods=["GET"])
@login_required
def api(isbn):

	# Sending an API request to goodreads.com
	res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "gwRyrKSkd1VvqI3NSac1Iw", "isbns": isbn})

	# Checking if isbn is valid and escaping a potential json.decoder error
	try:
		res = res.json()
	except:
		message = "Invalid ISBN"
		return render_template("error.html", message = message)	

	# Parsing the results
	res = res["books"]
	res = res[0]

	# Keys in res:
	# 	'id'
	# 	'isbn'
	# 	'isbn13'
	# 	'ratings_count'
	# 	'reviews_count',
	# 	'text_reviews_count'
	# 	'work_ratings_count'
	# 	'work_reviews_count'
	# 	'work_text_reviews_count'
	# 	'average_rating'

	# Fetching the book from our database
	book = db.execute("SELECT title, author, year FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()

	if len(book) == 0:
		message = "Sorry, there is no book with that ISBN"
		return render_template("error.html", message = message)

	title = book["title"]
	author = book["author"]
	year = book["year"]

	# Appending the title, author and year to the results we got from the API request
	res["title"] = title
	res["author"] = author
	res["year"] = year

	book = res

	return jsonify(book)