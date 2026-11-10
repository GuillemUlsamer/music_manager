import { Routes } from '@angular/router';
import { Runner } from './runner/runner';

export const routes: Routes = [
    { path: 'run/:name', component: Runner },
];