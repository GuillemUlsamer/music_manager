import { Routes } from '@angular/router';
import { Runner } from './runner/runner';
import { Playlists } from './playlists/playlists';

export const routes: Routes = [
    { path: 'run/:name', component: Runner },
    { path: 'playlists', component: Playlists },
    { path: '', redirectTo: '/playlists', pathMatch: 'full' },
];