import { ComponentProps } from 'streamlit-component-lib'
import InteractiveMap from './components/InteractiveMap'

function App() {
  // Mock props for development
  const mockProps: ComponentProps = {
    args: {
      height: 600,
      predictionOverlay: null
    },
    disabled: false,
    theme: {
      base: 'light',
      primaryColor: '#ff4b4b',
      backgroundColor: '#ffffff',
      secondaryBackgroundColor: '#f0f2f6',
      textColor: '#31333F',
      font: 'sans-serif'
    }
  }

  return (
    <div className="App">
      <InteractiveMap {...mockProps} />
    </div>
  )
}

export default App