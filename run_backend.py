import sys
sys.path.insert(0, "/Users/lukas/Documents/github/TRAILS")

from osm_prefill._wsgi import app

# Run without reloader to avoid the "-" path issue from stdin/heredoc
app.run(host="0.0.0.0", port=9090, debug=False, use_reloader=False)
