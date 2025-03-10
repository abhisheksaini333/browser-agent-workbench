const id = new URL(location.href).searchParams.get('action');
const endpoint = '/portal/action/' + encodeURIComponent(id);
fetch(endpoint).then(async response => {
  if (!response.ok) throw new Error('Browser session expired or unavailable');
  const action = await response.json();
  document.querySelector('#operation').textContent = action.kind + ' · expected resource version ' + action.precondition.version;
  document.querySelector('#sku').value = action.args.sku;
  document.querySelector('#quantity').value = action.args.quantity;
  document.querySelector('#transaction').dataset.ready = 'true';
}).catch(error => { document.querySelector('#status').textContent = error.message; });
document.querySelector('#transaction').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('button'); button.disabled = true;
  try {
    const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({args:{sku:document.querySelector('#sku').value, quantity:Number(document.querySelector('#quantity').value)}})});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || 'Submission failed');
    document.querySelector('#receipt').textContent = JSON.stringify(value);
    document.querySelector('#status').textContent = 'Receipt confirmed';
  } catch (error) { document.querySelector('#status').textContent = error.message; }
});
