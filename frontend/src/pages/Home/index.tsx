import React from 'react';
import { Navigate } from 'react-router';

const Home: React.FC = (): React.ReactElement => {
  return <Navigate to="/realised-volatility" replace />
}

export default Home;
