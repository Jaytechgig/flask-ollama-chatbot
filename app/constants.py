PLAYGROUND_HTML = """
<!DOCTYPE html>
<html>
  <head>
    <meta charset=utf-8/>
    <title>Tintu GraphiQL</title>
    <link rel="stylesheet"
          href="//cdn.jsdelivr.net/npm/graphiql@1.4.2/graphiql.min.css"/>
  </head>
  <body style="margin: 0;">
    <div id="graphiql" style="height: 100vh;"></div>
    <script
      crossorigin
      src="//cdn.jsdelivr.net/npm/react@16/umd/react.production.min.js">
    </script>
    <script
      crossorigin
      src="//cdn.jsdelivr.net/npm/react-dom@16/umd/react-dom.production.min.js">
    </script>
    <script
      src="//cdn.jsdelivr.net/npm/graphiql@1.4.2/graphiql.min.js">
    </script>
    <script>
      const graphQLFetcher = graphQLParams =>
        fetch('/graphql', {
          method: 'post',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(graphQLParams),
        }).then(response => response.json()).catch(() => response.text());

      ReactDOM.render(
        React.createElement(GraphiQL, { fetcher: graphQLFetcher }),
        document.getElementById('graphiql'),
      );
    </script>
  </body>
</html>
"""
