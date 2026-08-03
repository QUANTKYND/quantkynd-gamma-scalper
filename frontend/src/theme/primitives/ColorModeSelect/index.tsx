import { MenuItem, Select, type SelectProps, useColorScheme } from '@mui/material';

const ColorModeSelect: React.FC = (props: SelectProps): React.ReactElement | null => {
  const { mode, setMode } = useColorScheme();

  if ( !mode ) {
    return null;
  }

  return (
    <Select
      value={mode}
      onChange={(event) => setMode(event.target.value as 'light' | 'dark')}
      SelectDisplayProps={{
        // @ts-expect-error MUI's SelectDisplayProps does not expose custom data attributes.
        'data-screenshot': 'toggle-mode'
      }}
      {...props}
    >
      <MenuItem value="system">System</MenuItem>
      <MenuItem value="light">Light</MenuItem>
      <MenuItem value="dark">Dark</MenuItem>
    </Select>
  )
}

export default ColorModeSelect;
