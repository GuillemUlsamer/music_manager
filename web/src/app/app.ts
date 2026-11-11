import { Component , inject, OnInit} from '@angular/core';
import { RouterOutlet, RouterLink } from '@angular/router';
import { Api } from './api';

@Component({
  imports: [RouterOutlet, RouterLink],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})

export class App implements OnInit {
  api = inject(Api);

  ngOnInit() {
    this.api.status().subscribe(s => this.api.running.set(s.running));
  }
}