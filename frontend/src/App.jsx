import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { FilterProvider } from './lib/filters'
import Layout from './components/Layout'
import Login from './pages/Login'
import { Logo, Skeleton } from './components/ui'

// route-level code splitting: charts / chat code is only downloaded when the page is opened
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Products = lazy(() => import('./pages/Products'))
const Customers = lazy(() => import('./pages/Customers'))
const Fulfilment = lazy(() => import('./pages/Fulfilment'))
const Compare = lazy(() => import('./pages/Compare'))
const Orders = lazy(() => import('./pages/Orders'))
const Analyst = lazy(() => import('./pages/Analyst'))
const Admin = lazy(() => import('./pages/Admin'))
const Definitions = lazy(() => import('./pages/Definitions'))

function Guard({ feature, children }) {
  const { user } = useAuth()
  return user.features.includes(feature) ? children : <Navigate to="/" replace />
}

const Fallback = () => <div className="space-y-4 p-6" role="status" aria-label="Loading"><Skeleton className="h-10 w-64" /><Skeleton className="h-40 w-full" /></div>

function Shell() {
  const { user, loading } = useAuth()
  if (loading) return <div className="app-bg grid h-full place-items-center"><div className="animate-pulse"><Logo size={44} /></div></div>
  if (!user) return <Login />
  return (
    <FilterProvider>
      <Suspense fallback={<Fallback />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Guard feature="dashboard"><Dashboard /></Guard>} />
            <Route path="products" element={<Guard feature="dashboard"><Products /></Guard>} />
            <Route path="customers" element={<Guard feature="dashboard"><Customers /></Guard>} />
            <Route path="fulfilment" element={<Guard feature="dashboard"><Fulfilment /></Guard>} />
            <Route path="compare" element={<Guard feature="dashboard"><Compare /></Guard>} />
            <Route path="orders" element={<Guard feature="orders"><Orders /></Guard>} />
            <Route path="analyst" element={<Guard feature="chat"><Analyst /></Guard>} />
            <Route path="admin" element={<Guard feature="audit"><Admin /></Guard>} />
            <Route path="definitions" element={<Definitions />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </FilterProvider>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  )
}
