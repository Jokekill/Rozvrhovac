import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const LINKS: [string, string][] = [
  ['/', 'Rozvrh'],
  ['/solver', 'Solver'],
  ['/versions', 'Verze'],
  ['/activities', 'Aktivity'],
  ['/individual-lessons', 'Individuální výuka'],
  ['/students', 'Studenti'],
  ['/teachers', 'Učitelé'],
  ['/rooms', 'Učebny'],
  ['/groups', 'Skupiny'],
  ['/availability', 'Dostupnost'],
  ['/import', 'Import'],
  ['/settings', 'Nastavení'],
]

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Rozvrhovač</span>
        <nav>
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="page">{children}</main>
    </div>
  )
}
