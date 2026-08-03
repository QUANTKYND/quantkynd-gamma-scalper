import React from 'react';
import { Breadcrumbs as MuiBreadcrumbs, breadcrumbsClasses, Typography, styled } from '@mui/material';
import { NavigateNextRounded } from '@mui/icons-material';
import { useMatches } from 'react-router';

interface RouteHandle {
  name?: string;
}

const StyledBreadcrumbs = styled(MuiBreadcrumbs)(({ theme }) => ({
  margin: theme.spacing(1, 0),
  [`& .${breadcrumbsClasses.separator}`]: {
    color: (theme.vars || theme).palette.action.disabled,
    margin: 1,
  },
  [`& .${breadcrumbsClasses.ol}`]: {
    alignItems: 'center',
  },
}));

const Breadcrumbs: React.FC = (): React.ReactElement => {
  const matches = useMatches();
  const crumbs = matches.filter((match) => {
    const handle = match.handle as RouteHandle | undefined;
    return Boolean(handle?.name);
  });

  return (
    <StyledBreadcrumbs
      aria-label="breadcrumb"
      separator={<NavigateNextRounded fontSize="small" />}
    >
      {
        crumbs.map((match, index) => {
          const isLast = index === crumbs.length - 1;
          const handle = match.handle as RouteHandle;

          return (
            <Typography
              variant={'body1'}
              key={index}
              sx={{
                color: isLast ? 'text.primary' : 'text.secondary',
                fontWeight: isLast ? 600 : 400,
              }}
            >
              {handle.name}
            </Typography>
          )
        })
      }
    </StyledBreadcrumbs>
  )
}

export default Breadcrumbs;
