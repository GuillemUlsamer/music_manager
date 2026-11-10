import { Component, OnInit, OnDestroy, inject, signal, input} from '@angular/core';
import { Api, LogEvent } from '../api';
import { Subscription } from 'rxjs';
import { RouterLink } from '@angular/router';

interface Item {
  id: string | null;
  text: string;
  status: string;
  tag: string | null;  
}

@Component({
  imports: [RouterLink],
  selector: 'app-runner',
  styleUrl: './runner.scss',
  templateUrl: './runner.html',
})

export class Runner implements OnInit, OnDestroy {
  api = inject(Api);
  private sub?: Subscription;
  items = signal<Item[]>([]);
  name = input.required<string>();

  ngOnInit() {
    this.sub = this.api.events().subscribe(e => { 
      this.apply(e);
    });
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
  }

  run (name: string) {
    this.items.set([]);
    this.api.run(name).subscribe(() => {
      this.api.running.set(true);
    });
  }

  stop() {
    this.api.stop().subscribe();
  }

  copyLog() {
    this.api.log().subscribe(log => {
      navigator.clipboard.writeText(log);
    });
  }

  private apply(e: LogEvent) {
    const id = JSON.stringify(e.song_id);
    if (e.kind === 'song') {
      this.items.update(i => [...i, { id, text: e.text, status: '', tag: null }]);
    } else if (e.kind === 'status') {
      this.items.update(i => 
        i.map(item => 
          item.id === id ? { ...item, status: e.text, tag: e.tag } : item
        )
      );
    } else {
      this.items.update(i => [...i, { id: null, text: e.text, status: '', tag: null }]);
      if (e.text.startsWith('Finished') || e.text.startsWith('Stopped')) this.api.running.set(false);
    }
  }
}
