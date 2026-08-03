import { RouterProvider } from "react-router"
import { Provider } from "react-redux"
import router from "./routes"
import { store } from "./store"
import AppTheme from "./theme"

const App: React.FC = (): React.ReactElement => {
  return (
    <Provider store={store}>
      <AppTheme>
        <RouterProvider router={router} />
      </AppTheme>
    </Provider>
  )
}

export default App
