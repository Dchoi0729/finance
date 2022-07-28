import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd, percent, percent2

# https://scrimba.com/learn/learnreact
# https://cs50.readthedocs.io/heroku/
# export API_KEY=pk_01c5fa2829cb450e91de45efa0669518
# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Returns cash owned by user
    cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]

    # Returns symbol, the total share for that symbol, the total price bought for that symbol from data base
    db_data = db.execute(
        "SELECT symbol, SUM(shares), SUM(total_price) FROM transactions WHERE user_id=? GROUP BY symbol", session["user_id"])

    # Populates portfolio with dictionaries of currently owned stok with all relevant information
    curr_owned = currently_owned()
    portfolio = get_portfolio()[1]

    return render_template("index.html", portfolio=portfolio, cash=usd(cash), total=usd(get_portfolio()[0]))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    """Add cash, change password and show overall profitability"""

    seed_cash = db.execute("SELECT seed_money FROM users WHERE id=?", session["user_id"])[0]["seed_money"]
    left_cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]

    # If user sent a post request by filling up one of the forms
    if request.method == "POST":

        # If user wants to add more cash
        new_cash = 0
        if request.form.get("cash") and not request.form.get("cash") == 0:
            new_cash = int(request.form.get("cash"))

            # Update users table
            db.execute("UPDATE users SET cash=?, seed_money=? WHERE id=?",
                       left_cash+new_cash, seed_cash+new_cash, session["user_id"])

            if new_cash > 0:
                flash("Cash added")
            else:
                flash("Cash deducted")

        # If user wants to change password
        if request.form.get("oldpassword") and request.form.get("password") and request.form.get("confirmation"):

            # Check if original password is correct
            original_pwd = db.execute("SELECT hash FROM users WHERE id=?", session["user_id"])[0]["hash"]
            if not check_password_hash(original_pwd, request.form.get("oldpassword")):
                return apology("Original password is incorrect")

            # Check if confirmation and new password match
            new_pwd = request.form.get("password")
            confirm_pwd = request.form.get("confirmation")
            if not new_pwd == confirm_pwd:
                return apology("New password and confirmation password don't match")

            # Update users table
            db.execute("UPDATE users SET hash=? WHERE id=?", generate_password_hash(new_pwd), session["user_id"])
            flash("Password updated")

        total = get_portfolio()[0]
        cash = seed_cash+new_cash
        percent_change = (total-cash)/cash * 100

        return redirect("/account")

    # If user clicked on navbar
    if request.method == "GET":
        total = get_portfolio()[0]
        percent_change = (total-seed_cash)/seed_cash * 100
        return render_template("profile.html", money=usd(seed_cash), total=usd(get_portfolio()[0]), change=percent2(percent_change))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # If user didn't provide a symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Missing Symbol")

        # If provided symbol is not valid
        data = lookup(symbol)
        if not data:
            return apology("Invalid Symbol")

        # If user didn't provide a share number
        if not request.form.get("shares"):
            return apology("Missing shares")

        shares = request.form.get("shares")
        if not shares.isdigit():
            return apology("Provide int for shares")

        # If user inputted a negative amount of shares
        shares = int(shares)
        if shares < 0:
            return apology("Negative shares")

        # Check if user has enough money
        desired = data["price"] * shares
        balance = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]
        if desired > balance:
            return apology("Not enough money")

        # Get current time
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d %H:%M:%S")

        # Record purchase to database (transactions table)
        db.execute("INSERT INTO transactions(user_id,symbol,shares,total_price,time) Values (?,?,?,?,?)",
                   session["user_id"], symbol, shares, desired, date_time)

        # Change remaining balance (users table)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance - desired, session["user_id"])

        flash('Bought!')
        return redirect("/")

    if request.method == "GET":
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    history = db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC", session["user_id"])
    for row in history:
        price = row["total_price"]
        shares = row["shares"]
        if not shares == 0:
            row["price"] = usd(price/shares)
        else:
            row["price"] = 0

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        session["username"] = request.form.get("username")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User sent a post request with symbol
    if request.method == "POST":

        data = lookup(request.form.get("symbol"))

        # If symbol is valid
        if not data == None:
            return render_template("quoted.html", name=data["name"], symbol=data["symbol"], price=usd(data["price"]))
        else:
            return apology("Invalid symbol")

    # User clicked on quote tab on navbar
    if request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Rser sent a register post request
    if request.method == "POST":

        # Check to see if username was provided
        user = request.form.get("username")
        if not user:
            """
            flash("Please provide a username")
            return redirect("/register")
            """
            return apology("Please provide a username")

        # Check to see if username already exists in database
        db_user = db.execute("SELECT * FROM users WHERE username=?", user)
        if db_user:
            """
            flash("Username already exists")
            return redirect("/register")
            """
            return apology("Username already exists")

        # Check to see if password and confirmation password was provided
        pwd = request.form.get("password")
        pwd_confirm = request.form.get("confirmation")
        if not pwd or not pwd_confirm:
            """
            flash("Please provide a password")
            return redirect("/register")
            """
            return apology("Please provide a password")

        # Check to see if password and confirmation password are equal
        if pwd != pwd_confirm:
            """
            flash("Password and confirmation password do not match")
            return redirect("/register")
            """
            return apology("Password and confirmation password do not match")

        # Adds username and password to database
        db.execute("INSERT INTO users(username,hash) VALUES (?,?)", user, generate_password_hash(pwd))

        # Remember which user has logged in
        rows = db.execute("SELECT * FROM users WHERE username = ?", user)
        session["user_id"] = rows[0]["id"]
        session["username"] = user

        flash('Registered!')
        return redirect("/")

    # User wants to register via the reigster nav tab
    if request.method == "GET":
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # List of symbol and shares of stocks currently owned by user
    list_of_symbol = currently_owned()

    # User clicked on sell tab on navbar
    if request.method == "GET":
        return render_template("sell.html", stocklist=list_of_symbol)

    # User sent a sell post request
    if request.method == "POST":

        # Check to see if symbol was provided
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Choose stock")

        # Check to see if user owns symbol
        if symbol not in list_of_symbol:
            return apology("You do not own that stock")

        # Check to see if shares was provided
        shares = request.form.get("shares")
        if not shares:
            return apology("Choose shares")

        # Check to see if shares provided is an integer
        if not shares.isdigit():
            return apology("Provide int for shares")

        # Check to see if user has that many shares
        shares = int(shares)
        curr_shares = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id=? AND symbol=?",
                                 session["user_id"], symbol)[0]["SUM(shares)"]
        if curr_shares < shares:
            return apology("You don't have that many shares")

        # Check to see if user gave positive share value
        if shares < 0:
            return apology("Can't sell negative shares")

        # Get current time
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d %H:%M:%S")

        # Get current price
        curr_price = -1 * lookup(symbol)["price"]
        total_price = shares * curr_price
        shares = -1 * shares

        # Record purchase to database (transactions table)
        db.execute("INSERT INTO transactions(user_id,symbol,shares,total_price,time) Values (?,?,?,?,?)",
                   session["user_id"], symbol, shares, total_price, date_time)

        # Add cash to user
        init_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        db.execute("UPDATE users SET cash = ? WHERE id = ?",  init_cash+-1*total_price, session["user_id"])

        # If user sold all shares of a specific stock, record to no_stock table
        remaining_shares = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id=? AND symbol=?",
                                      session["user_id"], symbol)[0]["SUM(shares)"]
        if remaining_shares == 0:
            last_id = db.execute("SELECT id FROM transactions WHERE symbol=? AND user_id=? ORDER BY id DESC LIMIT 1",
                                 symbol, session["user_id"])[0]["id"]
            db.execute("INSERT INTO no_stock(user_id, symbol, sold_id) Values(?,?,?)", session["user_id"], symbol, last_id)

        flash('Sold!')
        return redirect("/")


# Returns json format of number of shares for given symbol parameter
@app.route("/selloption", methods=["GET"])
@login_required
def sell_data():
    symbol = request.args.get("stock")

    # Returns number of shares of stock currently owned by user
    shares = db.execute("SELECT SUM(shares) FROM transactions WHERE user_id=? AND symbol=?", session["user_id"], symbol)

    return jsonify(shares[0]["SUM(shares)"])


# Returns [stock_sum, portfolio], where stock_sum is the amount of money and portfolio is a list of dict with all stock
# Dict has keys symbol, name, shares, curr_price, percent_change, total_price
def get_portfolio():

    # Returns symbol, the total share for that symbol, the total price bought for that symbol from data base
    db_data = db.execute(
        "SELECT symbol, SUM(shares), SUM(total_price) FROM transactions WHERE user_id=? GROUP BY symbol", session["user_id"])

    # Populates portfolio with dictionaries of currently owned stok with all relevant information
    curr_owned = currently_owned()
    portfolio = []
    stock_sum = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]

    for stock in curr_owned:

        last_emptied = db.execute(
            "SELECT sold_id FROM no_stock WHERE user_id=? AND symbol=? ORDER BY id DESC LIMIT 1", session["user_id"], stock)
        start_id = 0

        # If the stock was all sold and bought again, reset starting id point to calculate all values
        if len(last_emptied) > 0:
            start_id = last_emptied[0]["sold_id"]

        db_data = db.execute(
            "SELECT SUM(shares), SUM(total_price) FROM transactions WHERE user_id=? AND symbol=? AND id > ?", session["user_id"], stock, start_id)

        shares = db_data[0]["SUM(shares)"]
        avg_price = db_data[0]["SUM(total_price)"] / shares
        curr_price = lookup(stock)["price"]

        temp_dict = {
            "symbol": stock,
            "name": lookup(stock)["name"],
            "shares": shares,
            "curr_price": usd(lookup(stock)["price"]),
            "percent_change": percent((curr_price - avg_price) / avg_price * 100),
            "total_price": usd(shares*curr_price)
        }

        portfolio.append(temp_dict)
        stock_sum = stock_sum + shares*curr_price

    return [stock_sum, portfolio]


# Returns a list of of symbols of stocks currently owned by user
def currently_owned():
    # Returns symbol of stocks and number of shares traded by user from data base
    db_data = db.execute("SELECT symbol, SUM(shares) FROM transactions WHERE user_id=? GROUP BY symbol", session["user_id"])

    # List of symbol and shares of stocks currently owned by user
    list_of_symbol = []

    for stock in db_data:
        if stock["SUM(shares)"] > 0:
            list_of_symbol.append(stock["symbol"])

    return list_of_symbol

