import { useState } from 'react'
import LabelingView from './components/LabelingView'

type View = 'home' | 'labeling'

export default function App() {
  const [view, setView] = useState<View>('home')

  if (view === 'labeling') {
    return <LabelingView />
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight text-gray-900 font-serif">αινίγματα</h1>
        <p className="text-lg text-gray-600">Ancient Greek manuscript explorer</p>

        <div className="flex flex-col items-center gap-3 pt-2">
          <button
            onClick={() => setView('labeling')}
            className="px-6 py-3 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 transition-colors"
          >
            Label Training Data
          </button>
        </div>

        <p className="text-sm text-gray-400">
          Under construction — see{' '}
          <a
            href="https://github.com/aenigmata"
            className="underline hover:text-gray-600"
            target="_blank"
            rel="noreferrer"
          >
            TODO.md
          </a>{' '}
          for the roadmap.
        </p>
      </div>
    </div>
  )
}
