import { useState } from 'react'
import HomePage from './components/HomePage'
import Architecture from './components/Architecture'
import ScenarioDemo from './components/ScenarioDemo'
import AgentDetail from './components/AgentDetail'

function App() {
  const [activeTab, setActiveTab] = useState('home')

  const tabs = [
    { id: 'home', label: '首页', icon: '🏠' },
    { id: 'architecture', label: '架构图', icon: '🏗️' },
    { id: 'scenario', label: '场景演示', icon: '🎬' },
    { id: 'agents', label: 'Agent详情', icon: '🤖' },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="text-3xl">🚗</div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                  CarSales
                </h1>
                <p className="text-xs text-slate-400">多Agent汽车销售自主成交系统</p>
              </div>
            </div>
            <nav className="flex gap-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    activeTab === tab.id
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  <span className="mr-2">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'home' && <HomePage onNavigate={setActiveTab} />}
        {activeTab === 'architecture' && <Architecture />}
        {activeTab === 'scenario' && <ScenarioDemo />}
        {activeTab === 'agents' && <AgentDetail />}
      </main>
    </div>
  )
}

export default App
