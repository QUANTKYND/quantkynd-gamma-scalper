import { AnalyticsRounded, DashboardRounded, ShowChartRounded } from "@mui/icons-material";
import { Box, Divider, drawerClasses, Drawer as MuiDrawer, List, ListItemButton, ListItemIcon, ListItemText, Stack, Typography, styled } from "@mui/material";
import { Link, useLocation } from "react-router";

const drawerWidth = 240;

const Drawer = styled(MuiDrawer)({
  width: drawerWidth,
  flexShrink: 0,
  boxSizing: 'border-box',
  [`& .${drawerClasses.paper}`]: {
    width: drawerWidth,
    boxSizing: 'border-box',
  }
});

const Sidebar: React.FC = (): React.ReactElement => {
  const location = useLocation();

  return (
    <Drawer
      variant="permanent"
      sx={{
        display: { xs: 'none', md: 'block' },
        [`& .${drawerClasses.paper}`]: { 
          backgroundColor: 'background.paper',
        },
      }}
    >
      <Stack sx={{ height: '100%' }}>
        <Stack direction="row" spacing={1.25} sx={{ px: 2.5, py: 2.25, alignItems: 'center' }}>
          <Box sx={{ width: 32, height: 32, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: 'primary.main', color: 'primary.contrastText' }}>
            <ShowChartRounded fontSize="small" />
          </Box>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: 'text.primary', lineHeight: 1.2 }}>QuantKynd</Typography>
            <Typography variant="caption" color="text.secondary">Research console</Typography>
          </Box>
        </Stack>
        <Divider />
        <List sx={{ px: 1.25, py: 1.5 }}>
          <ListItemButton component={Link} to="/" selected={location.pathname === '/' || location.pathname === '/'} sx={{ borderRadius: 1 }}>
            <ListItemIcon sx={{ minWidth: 36 }}><DashboardRounded fontSize="small" /></ListItemIcon>
            <ListItemText primary="Home" slotProps={{ primary: { variant: 'body2', sx: { fontWeight: 600 } } }} />
          </ListItemButton>
          <ListItemButton component={Link} to="/realised-volatility" selected={location.pathname === '/realised-volatility' || location.pathname === '/'} sx={{ borderRadius: 1 }}>
            <ListItemIcon sx={{ minWidth: 36 }}><AnalyticsRounded fontSize="small" /></ListItemIcon>
            <ListItemText primary="Realised Volatility" slotProps={{ primary: { variant: 'body2', sx: { fontWeight: 600 } } }} />
          </ListItemButton>
        </List>
        <Box sx={{ mt: 'auto', p: 2.5 }}>
          <Typography variant="caption" color="text.secondary">Research environment</Typography>
        </Box>
      </Stack>
    </Drawer>
  )
}

export default Sidebar;
