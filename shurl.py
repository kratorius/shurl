import os
import string
import urllib2
from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request,  g, redirect, url_for, abort, render_template, flash
from wtforms import Form, StringField, validators


CURRPATH = os.path.dirname(os.path.realpath(__file__))
app = Flask(__name__)

app.config.update(dict(
    DATABASE=os.path.join(CURRPATH, 'urls.db'),
    DEBUG=True,
))
app.config.from_envvar("SHURL_SETTINGS", silent=True)


class AddForm(Form):
    slug = StringField("slug", [validators.Length(min=2)])
    url = StringField("URL", [validators.Length(min=2)])

    def validate_slug(form, field):
        validchars = string.ascii_letters + string.digits + "_-"
        for char in field.data:
            if char not in validchars:
                raise validators.ValidationError("slug can contain only alphanumeric characters and _ and -")

        if slug_exists(field.data):
            raise validators.ValidationError("a slug with this name already exists")

        existing_urls = [rule.rule[1:].split("/")[0] for rule in app.url_map._rules]
        if field.data in existing_urls:
            raise validators.ValidationError("this slug is reserved for internal use")

    def validate_url(form, field):
        url = field.data
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url
        errmsg = url + " is not a valid url"
        try:
            urllib2.urlopen(url, timeout=10)
        except:
            raise validators.ValidationError(errmsg)


def connect_db():
    """Connects to the specific database."""
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def init_db():
    """Creates the database tables."""
    with app.app_context():
        db = get_db()
        with app.open_resource(os.path.join(CURRPATH, 'schema.sql'), mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


@app.route("/", methods=["GET", "POST"])
def index():
    db = get_db()

    form = AddForm(request.form)
    if request.method == "POST" and form.validate():
        url = form.url.data
        slug = form.slug.data
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url

        db.execute("INSERT INTO entries (slug, url) VALUES (?, ?)", (slug, url))
        db.commit()

    cur = db.execute("SELECT slug, url, timestamp FROM entries ORDER BY timestamp DESC LIMIT 10")
    entries = cur.fetchall()
    cur = db.execute("SELECT slug, url, click_count FROM entries ORDER BY click_count DESC LIMIT 10")
    top_entries = cur.fetchall()

    return render_template("index.html",
                           base_url=request.host,
                           entries=entries,
                           top_entries=top_entries,
                           form=form)


@app.route("/all")
def all_entries():
    db = get_db()
    cur = db.execute("SELECT slug, url, timestamp, click_count FROM entries ORDER BY slug DESC")
    entries = cur.fetchall()
    return render_template("all.html", entries=entries)


@app.route("/search")
def search():
    db = get_db()
    query = request.args.get("q")
    cur = db.execute(
        "SELECT slug, url, timestamp FROM entries WHERE slug LIKE ? OR url LIKE ? ORDER BY timestamp DESC",
        ["%%%s%%" % query, "%%%s%%" % query]
    )
    entries = cur.fetchall()
    return render_template("search.html",
                           query=query,
                           entries=entries)


@app.route("/delete/<path:slug>")
def delete(slug):
    db = get_db()
    db.execute("DELETE FROM entries WHERE slug = ?", [slug])
    db.commit()
    return redirect(url_for("index"))


@app.route("/<path:slug>")
def redir(slug):
    """Catch everything else"""
    db = get_db()
    cur = db.execute("SELECT url FROM entries WHERE slug = ?", [slug])
    results = cur.fetchall()
    if not results or len(results) != 1:
        return redirect(url_for("search", q=slug))
    db.execute("UPDATE entries SET click_count = click_count + 1 WHERE slug = ?", [slug])
    db.commit()
    url = results[0][0]
    return redirect(url)


def slug_exists(slug):
    db = get_db()
    cur = db.execute("SELECT url FROM entries WHERE slug = ?", [slug])
    results = cur.fetchall()
    return bool(results)


if __name__ == '__main__':
    init_db()
    app.run()