self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "New Arbitrage Alert!";
  const options = {
    body: data.body || "We found new surebets or middles in your favorite leagues.",
    icon: "/static/icons/icon.png"
  };
  event.waitUntil(self.registration.showNotification(title, options));
});
