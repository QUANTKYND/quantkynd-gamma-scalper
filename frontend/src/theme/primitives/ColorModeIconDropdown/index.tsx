import { Box, IconButton, Menu, MenuItem, useColorScheme, type IconButtonProps } from '@mui/material';
import { LightMode, DarkMode } from '@mui/icons-material';
import React, { useState } from 'react';

const ColorModeIconDropdown: React.FC<IconButtonProps> = (props): React.ReactElement => {
  const { mode, systemMode, setMode } = useColorScheme();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  const handleClick = (event: React.MouseEvent<HTMLElement>): void => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = (): void => {
    setAnchorEl(null);
  }

  const handleModeChange = (targetMode: 'light' | 'dark' | 'system'): void => {
    setMode(targetMode);
    handleClose();
  }

  if ( !mode ) {
    return (
      <Box
        data-screenshot="toggle-mode"
        sx={(theme) => ({
          verticalAlign: 'bottom',
          display: 'inline-flex',
          width: '2.25rem',
          height: '2.25rem',
          borderRadius: (theme.vars || theme).shape.borderRadius,
          border: '1px solid',
          borderColor: (theme.vars || theme).palette.divider,
        })}
      />
    )
  }

  const resolvedMode = (systemMode || mode) as 'light' | 'dark';
  const icon = {
    light: <LightMode />,
    dark: <DarkMode />,
  }[resolvedMode];
  return (
    <React.Fragment>
      <IconButton
        data-screenshot="toggle-mode"
        onClick={handleClick}
        size={'small'}
        aria-controls={open ? 'color-scheme-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        {...props}
      >
        {icon}
      </IconButton>
      <Menu
        id={'color-scheme-menu'}
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        slotProps={{
          paper: {
            variant: 'outlined',
            elevation: 0,
            sx: {
              my: '4px',
            }
          }
        }}
        transformOrigin={{
          horizontal: 'right',
          vertical: 'top',
        }}
        anchorOrigin={{
          horizontal: 'right',
          vertical: 'bottom',
        }}
      >
        <MenuItem selected={mode === 'system'} onClick={() => handleModeChange('system')}>System</MenuItem>
        <MenuItem selected={mode === 'light'} onClick={() => handleModeChange('light')}>Light</MenuItem>
        <MenuItem selected={mode === 'dark'} onClick={() => handleModeChange('dark')}>Dark</MenuItem>
      </Menu>
    </React.Fragment>
  )
}

export default ColorModeIconDropdown;
