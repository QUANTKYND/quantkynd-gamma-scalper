import { createBrowserRouter } from "react-router";
import MainLayout from "../layout/MainLayout";
import RealisedVolatility from "../pages/RealisedVolatility";
import Home from "../pages/Home";

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    handle: {
      name: 'Dashboard'
    },
    children: [
      {
        index: true,
        element: <Home />,
        handle: {
          name: 'RV Research'
        }
      },
      {
        path: 'realised-volatility',
        element: <RealisedVolatility />,
        handle: {
          name: 'Realised Volatility'
        }
      }
    ]
  }
]);

export default router;
