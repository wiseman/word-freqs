#!/usr/bin/env python

# Web app, based on web.py, to analyze term frequency of documents
# referenced by URL.
#
# John Wiseman <jjwiseman@gmail.com>
# 2/12/2009

import os
import os.path
import random
import urllib
import re
import StringIO
import md5
import pprint
import string
import time
import urlparse
import math

# I'm using Python 2.5, which doesn't have the json module introduced
# in 2.6, so I'm using simple_json.
import simplejson as json

# Aaron Swartz's web.py webdev framework
import web

# Using matplotlib to generate charts.
import matplotlib
# Prepare to generate image files, not display charts in windows.
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# ------------------------------------------------------------
# web.py configuration
# ------------------------------------------------------------

# Setup URL mapping for web.py
# URL regex -> Page generating class name.

urls = [
    # Normal pages, more or less.
    '/', 'Index',
    '',  'Index',
    '/r', 'Result',
    '/i/(.*)', 'DynamicImage',
    
    # AJAX support URLS
    '/t', 'Tokenize',
    '/a', 'Analyze'
    ]

web.webapi.internalerror = web.debugerror
app = web.application(urls, globals())
render = web.template.render('templates/')


# ------------------------------------------------------------
# Page generating classese
# ------------------------------------------------------------

class Index:
    "Index page.  Uses the index.html template."
    def GET(self):
        return render.index()

class Analyze:
    """
    AJAX support URL.  Takes term frequency data and stop letters as
    input, returns a chart URL, the 10 most common terms, the
    frequency data and stop letters as output.  All input and output
    is in JSON format.  Supports only POST.
    """
    def GET(self):
        # Nobody should ever be trying to GET this.
        raise web.internalerror()

    def POST(self):
        i = web.input()
        freq_data = json.loads(i.freq_data)
        stop_letters = json.loads(i.stop_letters)

        # Remove terms with stop letters, make sure we have the
        # appropriate chart image.
        effective_freqs = remove_stops(freq_data, stop_letters)
        chart_url = ensure_chart(effective_freqs)

        result = {'freq_data': freq_data,
                  'stop_letters': stop_letters,
                  'chart_url': chart_url,
                  'most_common': most_common_terms(effective_freqs, 10)}
        web.header('Content-Type', 'text/x-json')
        return json.dumps(result)

class Tokenize:
    """
    AJAX support URL.  Takes a URL as input, returns term frequency
    data as output.  All input and output is in JSON format.  Supports
    only GET.
    """
    def GET(self):
        i = web.input()
        url = canonicalize_url(i.url)
        web.header('Content-Type', 'text/x-json')

        # If we run into trouble, return a JSON object with an "error"
        # property that the page can then display.
        try:
            html = urllib.urlopen(url).read()
        except:
            return app_error('Unable to read URL %s, please try another URL.' % (url,))
        
        freq_data = analyze_document(html)
        return json.dumps({'freq_data': freq_data})

class Result:
    "Results page.  Uses the result.html template."
    def GET(self):
        i = web.input()
        # If we didn't get the url parameter we expected, redirect to
        # the index.
        if not 'url' in i:
            raise web.seeother("/")
        return render.result(i.url)

class DynamicImage:
    """
    Handles the generated chart image URLS.  We could just put them
    under /static, but I like keeping them separate.
    """
    def GET(self, name):
        # Just return the contents of the file in the dynamic-images
        # directory.
        if name in os.listdir('dynamic-images'):
            web.header("Content-Type", content_type_for_file(name))
            return open('dynamic-images/%s' % (name,), "rb").read()
        else:
            web.notfound()


# ------------------------------------------------------------
# The real work gets done here.
# ------------------------------------------------------------

# ---------- Text analysis.

def analyze_document(html):
    """
    Takes HTML, converts it to straight text (simplemindedly) and
    returns a term frequency dictionary.
    """
    text = strip_html(html)
    tokens = tokenize(text)
    freq = {}
    for token in tokens:
        freq[token] = freq.get(token, 0) + 1
    return freq


def strip_html(html):
    "Strips out HTML tags."
    # We don't really deal with character sets; We assume every page
    # is unicode and we ignore characters that don't survive that
    # assumption.
    html = unicode(html, errors='ignore')
    html = html.encode('ascii', 'ignore')
    s = StringIO.StringIO()
    in_html = False
    for c in html:
        if in_html:
            if c == '>':
                in_html = False
            else:
                pass
        else:
            if c == '<':
                in_html = True
            else:
                s.write(c)
    return s.getvalue()


TOKENIZING_RE = re.compile('\W+', re.IGNORECASE | re.MULTILINE | re.UNICODE)
def tokenize(text):
    "Tokenizes text, using the standard \W+ regex."
    tokens = TOKENIZING_RE.split(string.lower(text))
    # Strip empty tokens
    tokens = [t for t in tokens if t != '']
    return tokens


def remove_stops(freq_data, stop_letters):
    """
    Returns a new frequency dictionary that does not include entries
    where the term has a stop letter.
    """
    new_freqs = {}
    for token in freq_data:
        if not word_contains_any_letter(token, stop_letters):
            new_freqs[token] = freq_data[token]
    return new_freqs


def most_common_terms(freq_data, n):
    "Returns the most frequent n terms."
    counts = [[term, freq_data[term]] for term in freq_data]
    counts.sort(key=lambda p: p[1])
    counts.reverse()
    return counts[0:min(n, len(counts))]


def word_contains_any_letter(word, letters):
    for l in letters:
        if l in word:
            return True
    return False


# ---------- Generating frequency charts.

def ensure_chart(freqs):
    """
    Returns the URL of a chart for the given frequency data.  If such
    a chart doesn't already exist, one is generated.
    """
    if chart_is_ready(freqs):
        return chart_url(freqs)
    else:
        generate_chart(freqs)
        return chart_url(freqs)

def generate_chart(freqs):
    "Uses matplotlib to generate a chart for given term frequency data."
    fig = plt.figure(figsize=(7,3.1))
    counts = [freqs[k] for k in freqs]
    counts.sort()
    counts.reverse()
    plt.title("Term Distribution", name="Helvetica", fontsize=11)
    plt.ylabel("Frequency", name="Helvetica", fontsize=9)
    plt.xlabel("Term Rank", name="Helvetica", fontsize="9")
    ax = fig.add_subplot(111)
    line, = ax.plot(range(1, len(counts)+1), counts)
    line.set_antialiased(True)
    line.set_linewidth(2.0)
    line.set_color('#8a87bc')
    line.set_linestyle('steps')
    for label in ax.xaxis.get_ticklabels():
        label.set_fontsize(9)
    for label in ax.yaxis.get_ticklabels():
        label.set_fontsize(9)
    fig.savefig(chart_path(freqs), facecolor='#c6e3fe', edgecolor='#c6e3fe')


def compute_chart_hash(freqs):
    """
    We cache charts in the filesystem.  We identify them using a hash
    based on the frequency data.
    """
    # Just use MD5 to hash a canonical JSON form of the frequency
    # data.
    m = md5.new()
    m.update(json.dumps(freqs, sort_keys=True))
    return m.hexdigest()


def chart_url(freqs):
    "Given frequency data, returns the URL of the appropriate chart."
    chart_hash = compute_chart_hash(freqs)
    return '/i/%s.png' % (chart_hash,)

def chart_path(freqs):
    """
    Given frequency data, returns the path to the chart image in the
    filesystem.
    """
    chart_hash = compute_chart_hash(freqs)
    return 'dynamic-images/%s.png' % (chart_hash,)

def chart_is_ready(freqs):
    "Checks whether a chart for given frequency data already exists."
    return os.path.exists(chart_path(freqs))



# ---------- Misc. utilities

def canonicalize_url(url):
    """
    Used to turn URLs typed by the user into real URLS.  Really just
    lets them leave off the "http://".
    """
    url_pieces = urlparse.urlsplit(url)
    if url_pieces[0] == '':
        url = 'http://' + url
    return url


CONTENT_TYPES = {"png":"images/png",
                 "jpg":"image/jpeg",
                 "gif":"image/gif",
                 "ico":"image/x-icon"}
def content_type_for_file(filename):
    "Returns the correct Content-Type for files we might use."
    extension = filename.split(".")[-1]
    return CONTENT_TYPES[extension]


def app_error(msg):
    """
    Creates a special 'error' JSON object that a page can display to
    the user.
    """
    error = {'error': msg}
    return json.dumps(error)



# Run the web app.

if __name__ == "__main__":
    app.run()

