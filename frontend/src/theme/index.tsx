import { createTheme, ThemeProvider } from "@mui/material";
import { useMemo, type PropsWithChildren } from "react";
import { colorSchemes, shadows, shape, typography } from "./primitives";
import { inputCustomizations } from "./customizations/inputs";
import { dataDisplayCustomizations } from "./customizations/dataDisplay";
import { feedbackCustomizations } from "./customizations/feedback";
import { navigationCustomizations } from "./customizations/navigation";
import { surfacesCustomizations } from "./customizations/surfaces";

const AppTheme: React.FC<PropsWithChildren> = ({ children }): React.ReactElement => {
  const theme = useMemo(() => {
    return createTheme({
      cssVariables: {
        colorSchemeSelector: 'data-mui-color-scheme',
        cssVarPrefix: 'template',
      },
      colorSchemes,
      shadows,
      shape,
      typography,
      components: {
        ...inputCustomizations,
        ...dataDisplayCustomizations,
        ...feedbackCustomizations,
        ...navigationCustomizations,
        ...surfacesCustomizations,
      }
    });
  }, []);
  
  return (
    <ThemeProvider theme={theme}>
      {children}
    </ThemeProvider>
  )
}

export default AppTheme;
