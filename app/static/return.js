initialize();

async function initialize() {
  const siteUrl = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
  const queryString = window.location.search;
  const urlParams = new URLSearchParams(queryString);
  const sessionId = urlParams.get('session_id');
  const response = await fetch(`/plans/session-status?session_id=${sessionId}`);
  const session = await response.json();

  if (session.status == 'open') {
    window.location.replace(siteUrl+'/plans/checkout')
  } else if (session.status == 'complete') {
    document.getElementById('success').classList.remove('hidden');
    document.getElementById('customer-email').innerHTML = session.customer_email
  }
}