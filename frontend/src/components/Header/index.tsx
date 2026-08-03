import { Stack } from '@mui/material';
import React from 'react';
import Breadcrumbs from '../Breadcrumbs';
import ColorModeIconDropdown from '../../theme/primitives/ColorModeIconDropdown';

const Header: React.FC = (): React.ReactElement => {
  return (
    <Stack
      direction={'row'}
      sx={{
        display: { xs: 'none', md: 'flex' },
        width: '100%',
        alignItems: { xs: 'flex-start', md: 'center' },
        justifyContent: 'space-between',
        maxWidth: { sm: '100%', md: '1700px' },
        pt: 1.5,
      }}
      spacing={2}
    >
      <Breadcrumbs />
      <ColorModeIconDropdown />
    </Stack>
  )
}

export default Header;
