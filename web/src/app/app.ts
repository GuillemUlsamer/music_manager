import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Api } from './api';

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})

export class App implements OnInit {
  protected readonly title = signal('web');
  private api = inject(Api);

  ngOnInit() {
    this.api.playlists().subscribe(p => {
      console.log(p);
    });
  }
}


