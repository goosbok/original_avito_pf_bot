// AdminPanel — picks the right admin page for the current admin route.
function AdminPanel({ route, onNavigate }) {
  if (route === 'admin-users')   return <AdminUsers onNavigate={onNavigate} />;
  if (route === 'admin-orders')  return <AdminOrders onNavigate={onNavigate} />;
  if (route === 'admin-support') return <AdminSupport onNavigate={onNavigate} />;
  return <AdminDashboard onNavigate={onNavigate} />;
}

Object.assign(window, { AdminPanel });
