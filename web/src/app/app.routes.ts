import { Routes } from '@angular/router';
import { Runner } from './runner/runner';
import { Playlists } from './playlists/playlists';
import { Settings } from './settings/settings';

export const routes: Routes = [
    { path: 'run/:name', component: Runner },
    { path: 'playlists', component: Playlists },
    { path: 'settings', component: Settings },
    { path: '', redirectTo: '/playlists', pathMatch: 'full' },
];