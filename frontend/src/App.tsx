import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ActivitiesPage } from './pages/ActivitiesPage'
import { AvailabilityPage } from './pages/AvailabilityPage'
import { GroupsPage } from './pages/GroupsPage'
import { ImportPage } from './pages/ImportPage'
import { IndividualLessonsPage } from './pages/IndividualLessonsPage'
import { RoomsPage } from './pages/RoomsPage'
import { SettingsPage } from './pages/SettingsPage'
import { SolverPage } from './pages/SolverPage'
import { StudentsPage } from './pages/StudentsPage'
import { TeachersPage } from './pages/TeachersPage'
import { TimetablePage } from './pages/TimetablePage'
import { VersionsPage } from './pages/VersionsPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<TimetablePage />} />
        <Route path="/solver" element={<SolverPage />} />
        <Route path="/versions" element={<VersionsPage />} />
        <Route path="/activities" element={<ActivitiesPage />} />
        <Route path="/individual-lessons" element={<IndividualLessonsPage />} />
        <Route path="/students" element={<StudentsPage />} />
        <Route path="/teachers" element={<TeachersPage />} />
        <Route path="/rooms" element={<RoomsPage />} />
        <Route path="/groups" element={<GroupsPage />} />
        <Route path="/availability" element={<AvailabilityPage />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
