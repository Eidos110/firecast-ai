import { jsx as _jsx } from "react/jsx-runtime";
import InteractiveMap from './components/InteractiveMap';
function App() {
    // Mock props for development
    const mockProps = {
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
    };
    return (_jsx("div", { className: "App", children: _jsx(InteractiveMap, { ...mockProps }) }));
}
export default App;
