import { Component , inject, OnInit} from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Api } from './api';

@Component({
  imports: [RouterOutlet],
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