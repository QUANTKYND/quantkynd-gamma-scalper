import { configureStore } from '@reduxjs/toolkit';
import { authApi } from './api/authApi';
import { rvApi } from './api/rvApi';

export const store = configureStore({
  reducer: {
    [authApi.reducerPath]: authApi.reducer,
    [rvApi.reducerPath]: rvApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(authApi.middleware, rvApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
