// This is your test publishable API key.
const stripe = Stripe("pk_test_51Rq0GgFL77NInx71h8wmvkiZXBk5gOmMjrGpxYKGOKYnNWTedniFvXmAzDrP057mXmx7LeUneYMGtjlsVBBrUyQC000IeRURuL");

initialize();

// Create a Checkout Session
async function initialize() {
  const fetchClientSecret = async () => {
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    let plan_id = window.location.pathname.replace(/\/$/, "").split("/").pop();
    const response = await fetch("/plans/create-checkout-session", {
      method: "POST",
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ plan_id: plan_id })
    });
    const { clientSecret } = await response.json();
    return clientSecret;
  };

  const checkout = await stripe.initEmbeddedCheckout({
    fetchClientSecret,
  });

  // Mount Checkout
  checkout.mount('#checkout');
}