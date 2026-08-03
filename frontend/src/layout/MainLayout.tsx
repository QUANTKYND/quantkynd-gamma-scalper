import { alpha, Box, CssBaseline, Stack } from '@mui/material';
import React from 'react';
import Sidebar from '../components/Sidebar';
import Navbar from '../components/Navbar';
import { Outlet } from 'react-router';
import Header from '../components/Header';

const MainLayout: React.FC = (): React.ReactElement => {
  return (
    <>
      <CssBaseline enableColorScheme />
      <Box
        sx={{
          display: 'flex'
        }}
      >
        <Sidebar />
        <Navbar />
        <Box
          component={'main'}
          sx={(theme) => ({
            flexGrow: 1,
            minWidth: 0,
            minHeight: '100vh',
            backgroundColor: theme.vars ? `rgba(${theme.vars.palette.background.defaultChannel} / 1)` : alpha(theme.palette.background.default, 1),
            overflow: 'auto',
          })}
        >
          <Stack
            spacing={2}
            sx={{
              mx: { xs: 2, sm: 3 },
              pb: 5,
              mt: { xs: 9, md: 0 },
              maxWidth: 1680,
            }}
          >
            <Header />
            <Outlet />
          </Stack>
        </Box>
      </Box>
    </>
  )
}

export default MainLayout;
